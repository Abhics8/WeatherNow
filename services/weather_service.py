import requests
import logging
import time
from rich.console import Console
from datetime import datetime
from typing import Optional, Dict, Any

console = Console()

def make_api_request_with_retry(url: str, timeout: int = 10, max_retries: int = 3) -> Optional[Dict[Any, Any]]:
    """
    Make API request with retry logic and exponential backoff.
    
    Args:
        url: API endpoint URL
        timeout: Request timeout in seconds
        max_retries: Maximum number of retry attempts
        
    Returns:
        JSON response or None on failure
    """
    for attempt in range(max_retries):
        try:
            response = requests.get(url, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except requests.Timeout:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                console.print(f"[yellow]API timeout - retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})[/yellow]")
                time.sleep(wait_time)
            else:
                console.print(f"[red]API timeout after {max_retries} attempts[/red]")
                return None
        except requests.RequestException as e:
            console.print(f"[red]API request failed: {str(e)}[/red]")
            return None
    return None

def get_rich_weather_data(city: str):
    """
    Fetch comprehensive weather data from Open-Meteo (Forecast + AQI).
    Returns a unified dictionary or None on error.
    """
    try:
        # 1. Geocoding with retry logic
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1&language=en&format=json"
        geo_res = make_api_request_with_retry(geo_url, timeout=10)
        
        if not geo_res or not geo_res.get('results'):
            console.print(f"[yellow]City '{city}' not found. Please check spelling.[/yellow]")
            return None
            
        loc = geo_res['results'][0]
        lat, lon = loc['latitude'], loc['longitude']
        client_timezone = loc.get('timezone', 'auto')
        
        # 2. Weather API (Current + Daily + Hourly + Minutely)
        w_url = (
            f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
            "&current=temperature_2m,relative_humidity_2m,apparent_temperature,is_day,weather_code,wind_speed_10m,uv_index,precipitation"
            "&hourly=temperature_2m,weather_code,uv_index,precipitation_probability,apparent_temperature"
            "&daily=weather_code,temperature_2m_max,temperature_2m_min,sunrise,sunset,uv_index_max,precipitation_sum"
            "&minutely_15=precipitation"
            "&forecast_days=8"  # Fetch 8 days to ensure full 7-day outlook
            f"&timezone={client_timezone}"
        )
        w_res = make_api_request_with_retry(w_url, timeout=10)
        if not w_res:
            console.print(f"[red]Failed to fetch weather data for {loc['name']}[/red]")
            return None
        
        # 3. Air Quality API (with fallback if it fails)
        aqi_url = f"https://air-quality-api.open-meteo.com/v1/air-quality?latitude={lat}&longitude={lon}&current=us_aqi"
        aqi_res = make_api_request_with_retry(aqi_url, timeout=10)
        # Fallback to 0 if AQI API fails (non-critical data)
        if not aqi_res:
            console.print(f"[yellow]Could not fetch air quality data (using default)[/yellow]")
            aqi_res = {'current': {'us_aqi': 0}}
        
        # 4. Construct Unified Data Object
        data = {
            "city": loc['name'],
            "country": loc.get('country', ''),
            "lat": lat,
            "lon": lon,
            "timezone": client_timezone,
            "current": {
                "temp": w_res['current']['temperature_2m'],
                "feels_like": w_res['current']['apparent_temperature'],
                "humidity": w_res['current']['relative_humidity_2m'],
                "wind_speed": w_res['current']['wind_speed_10m'],
                "uv_index": w_res.get('current', {}).get('uv_index', 0),
                "is_day": w_res['current']['is_day'],
                "weather_code": w_res['current']['weather_code'],
                "aqi": aqi_res.get('current', {}).get('us_aqi', 0),
                "precip": w_res['current']['precipitation']
            },
            "daily": [],
            "hourly": [],
            "minutely": []
        }
        
        # Process Daily (7 Days)
        daily = w_res['daily']
        for i in range(len(daily['time'])):
            data['daily'].append({
                "date": daily['time'][i],
                "code": daily['weather_code'][i],
                "max_temp": daily['temperature_2m_max'][i],
                "min_temp": daily['temperature_2m_min'][i],
                "sunrise": daily['sunrise'][i],
                "sunset": daily['sunset'][i],
                "uv_max": daily['uv_index_max'][i],
                "precip_sum": daily['precipitation_sum'][i]
            })
            
        # Process Hourly (Next 48 Hours)
        hourly = w_res['hourly']
        current_hour_idx = 0 
        # Find current hour index roughly
        now_str = datetime.now().isoformat()
        # Simple slice: assume start is close to 0 or match time. 
        # API returns from 00:00 of requested day. logic: just take first 48 from now if possible, or just first 48 returned
        # Better: just take first 48 items returned, as API handles "current" context if we asked for past days? API defaults to today.
        
        for i in range(min(48, len(hourly['time']))):
            data['hourly'].append({
                "time": hourly['time'][i],
                "temp": hourly['temperature_2m'][i],
                "feels_like": hourly['apparent_temperature'][i],
                "prob": hourly['precipitation_probability'][i],
                "code": hourly['weather_code'][i]
            })
            
        # Process Minutely (Next 60 mins - 4 steps of 15 min)
        if 'minutely_15' in w_res:
            mins = w_res['minutely_15']
            for i in range(min(4, len(mins['time']))):
                 data['minutely'].append({
                     "time": mins['time'][i],
                     "precip": mins['precipitation'][i]
                 })
            
        return data
        
    except Exception as e:
        console.print(f"[red]Error fetching data: {e}[/red]")
        return None

# Keep legacy function for DB compatibility
def get_weather_from_wttr(city: str):
    return get_rich_weather_data(city)

def get_desc_from_code(code):
    return "Variable"

# Helper functions for CLI tool
def save_weather_data(db, city: str, weather_data: dict):
    """Persist a current observation for a city. Accepts both the legacy
    wttr-style payload ('current_condition') and the rich Open-Meteo payload
    ('current'). Creates the Location on first sight. Returns True on success."""
    from models import Location, WeatherRecord

    city_key = city.strip().lower()
    location = db.query(Location).filter(Location.city == city_key).first()
    if location is None:
        location = Location(city=city_key)
        db.add(location)
        db.commit()
        db.refresh(location)

    if "current_condition" in weather_data:  # legacy / wttr.in format
        c = weather_data["current_condition"][0]
        record = WeatherRecord(
            location_id=location.id,
            temp_c=float(c["temp_C"]),
            temp_f=float(c.get("temp_F") or 0),
            humidity=float(c.get("humidity") or 0),
            wind_speed_kmph=float(c.get("windspeedKmph") or 0),
            condition_text=c.get("weatherDesc", [{}])[0].get("value", ""),
        )
    elif "current" in weather_data:  # rich Open-Meteo format
        c = weather_data["current"]
        temp_c = float(c.get("temp", 0))
        record = WeatherRecord(
            location_id=location.id,
            temp_c=temp_c,
            temp_f=temp_c * 9 / 5 + 32,
            humidity=float(c.get("humidity", 0)),
            wind_speed_kmph=float(c.get("wind_speed", 0)),
            condition_text=str(c.get("weather_code", "")),
        )
    else:
        return False

    db.add(record)
    db.commit()
    return True


def get_history_stats(db, city: str, days: int = 7):
    """Return a city's WeatherRecords from the last `days` days, newest first."""
    from datetime import datetime, timedelta, timezone
    from models import Location, WeatherRecord

    city_key = city.strip().lower()
    location = db.query(Location).filter(Location.city == city_key).first()
    if location is None:
        return []

    # naive UTC (matches SQLite's server_default func.now() storage)
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    return (
        db.query(WeatherRecord)
        .filter(WeatherRecord.location_id == location.id)
        .filter(WeatherRecord.timestamp >= cutoff)
        .order_by(WeatherRecord.timestamp.desc())
        .all()
    )

def export_history_to_file(db, city: str, output_file: str):
    """Export weather history to CSV/JSON file."""
    import json
    import pandas as pd
    
    # Get historical data (placeholder - would use actual DB)
    data = get_rich_weather_data(city)
    if not data:
        console.print(f"[red]Could not fetch data for {city}[/red]")
        return False
    
    try:
        if output_file.endswith('.json'):
            with open(output_file, 'w') as f:
                json.dump(data, f, indent=2)
        elif output_file.endswith('.csv'):
            # Convert to DataFrame for CSV export
            df = pd.DataFrame([data['current']])
            df.to_csv(output_file, index=False)
        else:
            console.print("[red]Unsupported file format. Use .json or .csv[/red]")
            return False
            
        console.print(f"[green]Data exported to {output_file}[/green]")
        return True
    except Exception as e:
        console.print(f"[red]Export failed: {str(e)}[/red]")
        return False

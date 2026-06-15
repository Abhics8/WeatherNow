import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime
import plotly.graph_objects as go
import folium
from streamlit_folium import st_folium
from streamlit_js_eval import get_geolocation

# --- 1. CONFIG & THEME SETUP ---
st.set_page_config(page_title="WeatherNow", page_icon="🌤️", layout="wide")

# Safe Import
try:
    from services.weather_service import get_rich_weather_data
except ImportError:
    st.error("Service Error. Please check deployment.")
    st.stop()

# Initialize Session State
if 'selected_city' not in st.session_state: st.session_state.selected_city = "New Delhi"
if 'favorites' not in st.session_state: st.session_state.favorites = ["New Delhi", "New York", "London"]

# --- DYNAMIC GRADIENT LOGIC ---
def get_weather_gradient(code, is_day):
    if is_day == 0: return 'linear-gradient(135deg, #0f2027 0%, #203a43 50%, #2c5364 100%)'
    if code in [0, 1]: return 'linear-gradient(135deg, #f6d365 0%, #fda085 100%)'
    if code in [2, 3, 45, 48]: return 'linear-gradient(135deg, #a1c4fd 0%, #c2e9fb 100%)'
    if code in [51, 53, 55, 61, 63, 65, 80, 81, 82]: return 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)'
    if code in [95, 96, 99]: return 'linear-gradient(135deg, #434343 0%, #000000 100%)'
    if code in [71, 73, 75, 77, 85, 86]: return 'linear-gradient(135deg, #e0eafc 0%, #cfdef3 100%)'
    return 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)'

# Fetch Data
with st.spinner("Loading..."):
    data = get_rich_weather_data(st.session_state.selected_city)

bg_gradient = 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)'
if data:
    bg_gradient = get_weather_gradient(data['current']['weather_code'], data['current']['is_day'])

# --- 2. CSS INJECTION (THEME 1 RESTORED) ---
st.markdown(f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
    
    html, body, [class*="css"] {{ font-family: 'Inter', sans-serif; }}
    [data-testid="stIcon"] {{ font-family: initial !important; }}
    
    .stApp {{
        background: {bg_gradient};
        background-attachment: fixed;
    }}
    
    #MainMenu {{visibility: hidden;}}
    footer {{visibility: hidden;}}
    header {{visibility: hidden;}}
    
    /* Metrics */
    [data-testid="stMetric"] {{
        background: rgba(255, 255, 255, 0.1);
        backdrop-filter: blur(10px);
        border-radius: 16px;
        border: 1px solid rgba(255, 255, 255, 0.18);
        padding: 20px;
        box-shadow: 0 8px 32px rgba(31, 38, 135, 0.37);
        text-align: center;
    }}
    [data-testid="stMetricValue"] {{ font-size: 2.5rem !important; color: white !important; font-weight: 700 !important; }}
    [data-testid="stMetricLabel"] {{ color: rgba(255,255,255,0.9) !important; text-transform: uppercase; letter-spacing: 1px; font-size: 0.9rem !important; }}
    
    /* Buttons */
    .stButton button {{
        background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%) !important;
        color: white !important;
        border: none !important;
        border-radius: 12px !important;
        padding: 10px 25px !important;
        font-weight: 600 !important;
        box-shadow: 0 4px 15px rgba(240, 147, 251, 0.4) !important;
        transition: all 0.3s ease !important;
    }}
    .stButton button:hover {{ transform: translateY(-2px) !important; box-shadow: 0 6px 25px rgba(240, 147, 251, 0.6) !important; }}
    
    /* Sidebar */
    section[data-testid="stSidebar"] {{ background: rgba(0,0,0,0.2); }}
    
    /* Hero */
    .hero-title {{ font-size: 4rem; font-weight: 800; margin-bottom: 0; text-shadow: 0 4px 8px rgba(0,0,0,0.2); }}
    .hero-sub {{ font-size: 1.5rem; font-weight: 400; opacity: 0.9; }}
    
    h1, h2, h3, p, span {{ color: white !important; }}
</style>
""", unsafe_allow_html=True)

# --- 3. SIDEBAR ---
with st.sidebar:
    st.markdown("### 🌤️ WeatherNow")
    
    # 3.1 Geolocation
    if st.checkbox("📍 Use My Location"):
        loc = get_geolocation()
        if loc:
            try:
                lat, lon = loc['coords']['latitude'], loc['coords']['longitude']
                rev = requests.get(f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}", headers={'User-Agent': 'WN/1.0'}, timeout=3).json()
                addr = rev.get('address', {})
                name = addr.get('city') or addr.get('town') or addr.get('village') or addr.get('county')
                if name and name != st.session_state.selected_city:
                    st.session_state.selected_city = name
                    st.rerun()
            except: pass

    st.markdown("---")
    
    # 3.2 UNIFIED CITY SEARCH
    # Consolidated List
    ALL_CITIES = sorted(list(set([
        # India
        "New Delhi", "Mumbai", "Bangalore", "Hyderabad", "Chennai", "Kolkata", "Pune", "Ahmedabad", "Jaipur", "Surat", 
        "Lucknow", "Chandigarh", "Goa", "Kochi", "Indore", "Nagpur", "Bhopal", "Visakhapatnam", "Patna", "Vadodara",
        "Ludhiana", "Agra", "Nashik", "Ranchi", "Raipur", "Meerut", "Rajkot", "Varanasi", "Srinagar", "Aurangabad", 
        "Amritsar", "Navi Mumbai", "Allahabad", "Howrah", "Jabalpur", "Gwalior", "Vijayawada", "Jodhpur", "Madurai",
        # USA
        "New York", "Los Angeles", "Chicago", "Houston", "Phoenix", "Philadelphia", "San Antonio", "San Diego", "Dallas", "San Jose", 
        "Austin", "Seattle", "Denver", "Boston", "Las Vegas", "Miami", "San Francisco", "Atlanta", "Detroit", "Washington DC",
        "Nashville", "Portland", "Oklahoma City", "Baltimore", "Louisville", "Milwaukee", "Albuquerque", "Tucson", "Fresno",
        "Sacramento", "Kansas City", "Mesa", "Charlotte", "Raleigh", "Omaha", "Minneapolis", "Tampa", "New Orleans",
        # Europe
        "London", "Paris", "Berlin", "Madrid", "Rome", "Amsterdam", "Vienna", "Lisbon", "Warsaw", "Prague", 
        "Budapest", "Stockholm", "Oslo", "Copenhagen", "Zurich", "Athens", "Dublin", "Brussels", "Helsinki", "Barcelona", 
        "Munich", "Milan", "Hamburg", "Naples", "Turin", "Valencia", "Seville", "Frankfurt", "Stuttgart", "Dusseldorf",
        "Lyon", "Marseille", "Manchester", "Birmingham", "Edinburgh", "Glasgow", "Krakow", "Gdańsk", "Sofia", "Bucharest",
        # Global
        "Tokyo", "Dubai", "Singapore", "Sydney", "Beijing", "Seoul", "Bangkok", "Istanbul", "São Paulo", "Toronto", 
        "Moscow", "Cairo", "Cape Town", "Rio de Janeiro", "Mexico City", "Buenos Aires", "Hong Kong", "Kuala Lumpur",
        "Manila", "Jakarta", "Ho Chi Minh City", "Shanghai", "Melbourne", "Auckland", "Bora Bora", "Maldives", "Santorini"
    ])))
    
    # Enable "Custom" entry by using a text input logic mixed with selectbox? 
    # Streamlit doesn't support "Combobox" directly yet. 
    # Best compromise: A Selectbox of all cities + text input if "Other" is selected? 
    # OR better: Just a massive Selectbox. If user needs custom, they can use a toggle.
    
    # Simplified: Just one Search Box (Selectbox)
    selected_from_list = st.selectbox("🔍 Search City", ["Type to search..."] + ALL_CITIES, index=0)
    
    if selected_from_list and selected_from_list != "Type to search...":
        st.session_state.selected_city = selected_from_list

    # Allow custom typing for unlisted cities
    st.markdown("**OR**")
    custom_city = st.text_input("Type any city name", placeholder="e.g. Smallville")
    if custom_city:
        st.session_state.selected_city = custom_city

    st.markdown("---")
    st.caption("Saved Places")
    for fav in st.session_state.favorites:
        if st.button(f"❤️ {fav}", key=fav, width='stretch'):
            st.session_state.selected_city = fav

# --- 4. MAIN CONTENT ---
if not data:
    st.error(f"⚠️ Could not load weather data for '{st.session_state.selected_city}'. Please try a different city or check your internet connection.")
    st.info("💡 Try selecting a city from the sidebar dropdown instead of typing.")
    st.stop()
    
curr = data['current']
daily = data['daily'][0]

# HERO SECTION
c_hero, c_anim = st.columns([2, 1])
with c_hero:
    st.markdown(f"<div class='hero-title'>{round(curr['temp'])}°</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='hero-sub'>{data['city']}</div>", unsafe_allow_html=True)
    st.markdown(f"**Feels like {round(curr['feels_like'])}°** • {curr.get('is_day') and 'Day' or 'Night'}")
with c_anim:
    st.metric("Condition", f"{curr['uv_index']} UV", "High" if curr['uv_index']>5 else "Normal")

st.markdown("<br>", unsafe_allow_html=True)

# METRICS GRID
c1, c2, c3, c4 = st.columns(4)
with c1: st.metric("💧 Humidity", f"{curr['humidity']}%")
with c2: st.metric("💨 Wind", f"{curr['wind_speed']} km/h")
with c3: st.metric("🌅 Sunrise", datetime.fromisoformat(daily['sunrise']).strftime('%H:%M'))
with c4: st.metric("🍃 Air Quality", f"{curr['aqi']}")

# TABS
st.markdown("<br>", unsafe_allow_html=True)
t1, t2, t3, t4 = st.tabs(["📅 Forecast", "🗺️ Radar", "ℹ️ Details", "🧠 AI Predict & Anomalies"])

with t1:
    hourly_df = pd.DataFrame(data['hourly'])
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=hourly_df['time'], y=hourly_df['temp'],
        mode='lines', line=dict(color='white', width=3),
        fill='tozeroy', fillcolor='rgba(255,255,255,0.2)'
    ))
    fig.update_layout(
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color='white'), margin=dict(t=10, l=0, r=0, b=0),
        height=250, xaxis=dict(showgrid=False), yaxis=dict(showgrid=False)
    )
    st.plotly_chart(fig, width='stretch')
    
    st.markdown("#### 7-Day Outlook")
    cols = st.columns(7)
    for i, day in enumerate(data['daily'][:7]): # Fixed truncated forecast
        name = datetime.fromisoformat(day['date']).strftime("%a")
        with cols[i]:
            st.markdown(f"**{name}**")
            st.markdown(f"{round(day['max_temp'])}° / {round(day['min_temp'])}°")

with t2:
    m = folium.Map(location=[data['lat'], data['lon']], zoom_start=9, tiles='CartoDB dark_matter')
    folium.TileLayer(
        tiles="https://tile.rainviewer.com/v2/radar/nowcast_loop/512/{z}/{x}/{y}/2/1_1.png",
        attr="RainViewer", overlay=True, name="Rain", opacity=0.7
    ).add_to(m)
    st_folium(m, height=400, width='stretch')

with t3:
    st.json(curr)

with t4:
    st.markdown("### 🔬 PyTorch LSTM & Anomaly Detection Pipeline")
    st.write("Fetching 30 days of temperature records from Open-Meteo...")
    
    # Imports
    try:
        from ml.forecast import train_lstm, mc_dropout_predict
        from ml.anomaly import detect_anomalies
        import numpy as np
    except Exception as e:
        st.error(f"Error importing ML modules: {e}")
        st.stop()
        
    lat = data['lat']
    lon = data['lon']
    history_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=temperature_2m_max&past_days=30&forecast_days=1&timezone=auto"
    
    try:
        history_res = requests.get(history_url, timeout=10).json()
        history_temps = history_res['daily']['temperature_2m_max']
        dates = history_res['daily']['time']
    except Exception as e:
        history_temps = []
        st.error(f"Could not load historical temperatures: {e}")
        
    if len(history_temps) >= 15:
        # 1. Anomaly Detection (using rolling window of 7)
        anom_res = detect_anomalies(history_temps, z_thresh=2.0, window=7)
        anom_indices = anom_res["anomaly_indices"]
        
        # Plot history with anomalies
        fig_anom = go.Figure()
        fig_anom.add_trace(go.Scatter(
            x=dates, y=history_temps,
            mode='lines+markers', name='Max Temp (°C)',
            line=dict(color='rgba(255,255,255,0.7)', width=2)
        ))
        
        # Highlight anomalies
        if anom_indices:
            anom_dates = [dates[idx] for idx in anom_indices]
            anom_vals = [history_temps[idx] for idx in anom_indices]
            fig_anom.add_trace(go.Scatter(
                x=anom_dates, y=anom_vals,
                mode='markers', name='Anomaly 🚨',
                marker=dict(color='#ff576c', size=10, symbol='circle')
            ))
            st.warning(f"Detected **{len(anom_indices)}** temperature anomalies in the past 30 days!")
        else:
            st.success("No temperature anomalies detected in the past 30 days.")
            
        fig_anom.update_layout(
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
            font=dict(color='white'), margin=dict(t=20, l=0, r=0, b=0),
            height=300, xaxis=dict(showgrid=False), yaxis=dict(showgrid=False)
        )
        st.plotly_chart(fig_anom, use_container_width=True)
        
        # 2. LSTM Prediction
        st.markdown("#### 🔮 LSTM Deep Learning Prediction")
        
        with st.spinner("Running PyTorch LSTM model..."):
            try:
                # Train live on the fly
                model, stats = train_lstm(history_temps, seq_len=7, epochs=80)
                
                # Predict next day
                recent_window = history_temps[-7:]
                pred_mean, pred_lower, pred_upper = mc_dropout_predict(model, recent_window, stats, n_samples=50, ci=0.95)
                
                # Show prediction details
                st.markdown(f"""
                <div style='background: rgba(255, 255, 255, 0.1); backdrop-filter: blur(10px); 
                            padding: 25px; border-radius: 16px; border: 1px solid rgba(255, 255, 255, 0.18); 
                            text-align: center; margin: 20px 0;'>
                    <h4 style='color: rgba(255,255,255,0.9); margin: 0; font-size: 1.1rem; text-transform: uppercase;'>LSTM Next-Day Max Temp Prediction</h4>
                    <h1 style='color: #fda085; font-size: 3.5rem; margin: 15px 0; font-weight: 800;'>{pred_mean:.1f}°C</h1>
                    <p style='color: white; margin: 0; font-size: 1.1rem;'>95% Confidence Interval: <strong>{pred_lower:.1f}°C to {pred_upper:.1f}°C</strong></p>
                    <p style='color: rgba(255,255,255,0.5); font-size: 0.8rem; margin-top: 10px;'>Model trained live using PyTorch LSTM & Monte Carlo Dropout uncertainty</p>
                </div>
                """, unsafe_allow_html=True)
            except Exception as e:
                st.error(f"Error training LSTM: {e}")
    else:
        st.warning("Not enough temperature history to run AI models.")


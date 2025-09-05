import streamlit as st
import pandas as pd
import requests
import altair as alt
from datetime import date

# ------------------------
# Streamlit Page Config
# ------------------------
st.set_page_config(
    page_title="NERIS Daily Incident Analysis",
    page_icon="📅",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ------------------------
# Custom Styling
# ------------------------
def load_css():
    """Injects custom CSS to style the dashboard with a NERIS-branded light theme."""
    st.markdown("""
        <style>
            :root {
                --primary-bg: #FFFFFF;
                --secondary-bg: #F0F2F5;
                --text-color: #002855;
                --accent-color-red: #E31C3D;
            }
            [data-testid="stAppViewContainer"] {
                background-color: var(--primary-bg);
            }
            .main .block-container, .main {
                background-color: var(--primary-bg);
                color: var(--text-color);
            }
            [data-testid="stSidebar"] {
                background-color: var(--secondary-bg);
            }
            h1, h2, h3 { color: var(--text-color); }
            p, .st-emotion-cache-1qg05j4, [data-testid="stMarkdownContainer"] { color: var(--text-color); }
            [data-testid="stMetricValue"] { color: var(--text-color); }
            .stDataFrame { border: 1px solid #E0E0E0; border-radius: 8px; }
        </style>
    """, unsafe_allow_html=True)

# ------------------------
# Data Handling
# ------------------------
@st.cache_data
def load_data(path: str) -> pd.DataFrame:
    """
    Loads and pre-processes the incident dataset.
    """
    df = pd.read_csv(path)
    required_cols = ['alarm_datetime', 'incident_description', 'city', 'state', 'response_time_minutes', 'latitude', 'longitude']
    df.dropna(subset=required_cols, inplace=True)

    df['alarm_datetime'] = pd.to_datetime(df['alarm_datetime'], errors='coerce', utc=True)
    df.dropna(subset=['alarm_datetime'], inplace=True)

    df['response_time_minutes'] = pd.to_numeric(df['response_time_minutes'], errors='coerce')
    df.dropna(subset=['response_time_minutes'], inplace=True)
    
    df['date'] = df['alarm_datetime'].dt.date
    return df

# ------------------------
# API & UI Functions
# ------------------------
@st.cache_data
def get_weather_for_day(lat: float, lon: float, day: date, api_key: str) -> dict | None:
    """
    Fetches daily aggregated weather data from OpenWeatherMap API.
    Returns None on failure to prevent displaying multiple errors.
    """
    url = f"https://api.openweathermap.org/data/3.0/onecall/day_summary?lat={lat}&lon={lon}&date={day.strftime('%Y-%m-%d')}&appid={api_key}&units=metric"
    try:
        response = requests.get(url)
        response.raise_for_status() # Will raise an exception for 4xx/5xx errors
        data = response.json()
        return {
            'max_temp_c': data.get('temperature', {}).get('max'),
            'total_precipitation_mm': data.get('precipitation', {}).get('total'),
        }
    except requests.RequestException:
        # Return None instead of calling st.error here to avoid flooding the UI
        return None

def render_top_days_analysis(df: pd.DataFrame):
    """Calculates and displays the top 10 busiest days."""
    st.header("Top 10 Busiest Days by Incident Count")
    
    daily_counts = df.groupby('date').size().reset_index(name='incident_count')
    top_10_days = daily_counts.sort_values(by='incident_count', ascending=False).head(10)
    top_10_days['formatted_date'] = pd.to_datetime(top_10_days['date']).dt.strftime('%A, %B %d, %Y')
    
    st.dataframe(
        top_10_days[['formatted_date', 'incident_count']].rename(columns={'formatted_date': 'Date', 'incident_count': 'Total Incidents'}),
        use_container_width=True, hide_index=True
    )
    return top_10_days

def render_weather_correlation(df: pd.DataFrame, top_10_df: pd.DataFrame, api_key: str):
    """Fetches weather data for top days and shows correlation plots."""
    st.header("Weather Correlation for Top 10 Busiest Days")
    
    weather_data = []
    failed_requests = 0
    progress_bar = st.progress(0, text="Fetching weather data...")
    for i, row in enumerate(top_10_df.itertuples()):
        day_incidents = df[df['date'] == row.date]
        avg_lat = day_incidents['latitude'].mean()
        avg_lon = day_incidents['longitude'].mean()
        weather = get_weather_for_day(avg_lat, avg_lon, row.date, api_key)
        
        if weather is None:
            failed_requests += 1
        else:
            weather_data.append(weather)
            
        progress_bar.progress((i + 1) / len(top_10_df), text=f"Fetching weather for {row.date.strftime('%Y-%m-%d')}...")
    
    progress_bar.empty()
    
    # If all requests failed, show a clear warning and stop.
    if failed_requests == len(top_10_df):
        st.warning("Could not fetch weather data. Please check your OpenWeatherMap API key and ensure your subscription plan includes access to the 'One Call API 3.0' for historical data.", icon="🔑")
        return

    weather_df = pd.DataFrame(weather_data)
    # Filter the original top_10_df to only include days where weather was successfully fetched
    successful_days_df = top_10_df.iloc[:-failed_requests if failed_requests > 0 else len(top_10_df)].reset_index()
    correlation_df = pd.concat([successful_days_df, weather_df], axis=1)

    col1, col2 = st.columns(2)
    with col1:
        temp_chart = alt.Chart(correlation_df).mark_circle(size=100, opacity=0.8).encode(
            x=alt.X('max_temp_c:Q', title='Max Temperature (°C)'),
            y=alt.Y('incident_count:Q', title='Incident Count'),
            tooltip=['formatted_date', 'incident_count', 'max_temp_c']
        ).properties(title='Incidents vs. Max Temperature').interactive()
        st.altair_chart(temp_chart, use_container_width=True, theme="streamlit")
        
    with col2:
        precip_chart = alt.Chart(correlation_df).mark_circle(size=100, opacity=0.8).encode(
            x=alt.X('total_precipitation_mm:Q', title='Total Precipitation (mm)'),
            y=alt.Y('incident_count:Q', title='Incident Count'),
            tooltip=['formatted_date', 'incident_count', 'total_precipitation_mm']
        ).properties(title='Incidents vs. Precipitation').interactive()
        st.altair_chart(precip_chart, use_container_width=True, theme="streamlit")

def render_daily_details(df: pd.DataFrame, selected_day: date):
    """Displays a detailed breakdown of incidents for a selected day."""
    st.header(f"Detailed Analysis for: {selected_day.strftime('%A, %B %d, %Y')}")
    day_df = df[df['date'] == selected_day]
    
    if day_df.empty:
        st.warning("No data available for the selected day.")
        return

    # Key Metrics
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Incidents", f"{len(day_df):,}")
    busiest_hour = day_df['alarm_datetime'].dt.hour.value_counts().idxmax()
    col2.metric("Busiest Hour", f"{busiest_hour}:00 - {busiest_hour+1}:00")
    top_incident = day_df['incident_description'].value_counts().idxmax()
    col3.metric("Most Common Incident", top_incident)
    
    st.divider()
    
    # Full data table
    st.subheader("All Incidents on This Day")
    display_cols = ['alarm_datetime', 'incident_description', 'city', 'state', 'response_time_minutes']
    st.dataframe(
        day_df[display_cols].rename(columns={
            'alarm_datetime': 'Time of Alarm',
            'incident_description': 'Description',
            'city': 'City',
            'state': 'State',
            'response_time_minutes': 'Response Time (Min)'
        }),
        use_container_width=True,
        hide_index=True
    )

# ------------------------
# Main Application
# ------------------------
def main():
    """Main function to orchestrate the dashboard's creation and logic."""
    load_css()
    st.title("NERIS Daily Incident Analysis 📅")

    with st.sidebar:
        st.header("API Configuration")
        api_key = st.text_input("OpenWeatherMap API Key", type="password", help="Your key for the One Call API 3.0")

    try:
        df = load_data('data/NERIS_COMPLETE_INCIDENTS.csv')
    except (FileNotFoundError, KeyError) as e:
        st.error(f"🚨 Error loading data: {e}")
        return

    top_10_df = render_top_days_analysis(df)
    
    st.divider()
    
    if api_key:
        render_weather_correlation(df, top_10_df, api_key)
        st.divider()

    selected_day_str = st.selectbox(
        "Select a day from the top 10 to see a detailed breakdown:",
        options=top_10_df['formatted_date'].tolist()
    )
    
    if selected_day_str:
        selected_day_obj = pd.to_datetime(selected_day_str).date()
        render_daily_details(df, selected_day_obj)

if __name__ == "__main__":
    main()


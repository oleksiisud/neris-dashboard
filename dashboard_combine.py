import streamlit as st
import pandas as pd
import altair as alt
import pydeck as pdk
import requests
from keplergl import KeplerGl
from streamlit_keplergl import keplergl_static
from streamlit_extras.mandatory_date_range import date_range_picker
from streamlit_dynamic_filters import DynamicFilters
from datetime import date
from global_land_mask import globe

# ------------------------
# Main Page Configuration
# ------------------------
st.set_page_config(
    page_title="NERIS Comprehensive Dashboard",
    page_icon="🔥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ------------------------
# Unified Styling
# ------------------------
def load_css():
    """Injects custom CSS for a consistent NERIS-branded light theme across all tabs."""
    st.markdown("""
        <style>
            :root {
                --primary-bg: #FFFFFF;
                --secondary-bg: #F0F2F5;
                --text-color: #002855;
                --accent-color-red: #E31C3D;
                --accent-color-blue: #0071BC;
            }
            [data-testid="stAppViewContainer"] { background-color: var(--primary-bg); }
            .main .block-container, .main { background-color: var(--primary-bg); color: var(--text-color); }
            [data-testid="stSidebar"] { background-color: var(--secondary-bg); }
            h1, h2, h3 { color: var(--text-color); }
            p, .st-emotion-cache-1qg05j4, [data-testid="stMarkdownContainer"] { color: var(--text-color); }
            [data-testid="stMetricValue"] { color: var(--text-color); }
            .stDataFrame { border: 1px solid #E0E0E0; border-radius: 8px; }
        </style>
    """, unsafe_allow_html=True)

# ------------------------
# Unified Data Loading
# ------------------------
@st.cache_data
def load_all_data(path: str) -> pd.DataFrame:
    """
    Loads and pre-processes the dataset with all columns and transformations needed by any dashboard tab.
    """
    df = pd.read_csv(path)
    # Datetime conversions
    for col in ['alarm_datetime', 'last_unit_cleared_datetime']:
        df[col] = pd.to_datetime(df[col], errors='coerce', utc=True)

    # Numeric conversions
    for col in ['latitude', 'longitude', 'response_time_minutes', 'units_responded', 'animals_rescued']:
         df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # Calculate new columns
    df['date'] = df['alarm_datetime'].dt.date
    df['mission_duration'] = (df['last_unit_cleared_datetime'] - df['alarm_datetime']).dt.total_seconds() / 60
    
    # Add land/water flag
    try:
        df['on_land'] = globe.is_land(df['latitude'], df['longitude'])
    except Exception:
        df['on_land'] = True
        
    # Fill missing values
    for col in ['patient_status', 'fire_suppression_effectiveness', 'incident_category', 'incident_description', 'city', 'state', 'incident_type']:
        df[col] = df[col].fillna('Unknown')
    
    # Create specific incident type for density map
    df['Specific Incident Type'] = df['incident_type'].str.split('||').str.get(-1)
        
    df.reset_index(drop=True, inplace=True)
    return df

# =================================================================================================
# TAB 1: 3D DENSITY MAP (Dashboard 00)
# =================================================================================================
def render_density_map_dashboard(df: pd.DataFrame):
    st.title("3D Incident Density Map")
    st.markdown("Visualize the density of incidents with a 3D heatmap.")

    # --- Filters for this tab ---
    filter_cols = st.columns(3)
    with filter_cols[0]:
        min_date_1 = df['alarm_datetime'].min().date()
        max_date_1 = df['alarm_datetime'].max().date()
        start_date, end_date = st.date_input("Date Range", value=(min_date_1, max_date_1), min_value=min_date_1, max_value=max_date_1, key="tab1_date")
    with filter_cols[1]:
        location_type = st.radio("Location Type", ('All', 'Land Only', 'Water Only'), key="tab1_location")
    with filter_cols[2]:
        incident_types = ['All'] + sorted(df['Specific Incident Type'].unique())
        selected_incident = st.selectbox("Specific Incident Type", options=incident_types, key="tab1_incident")

    # Apply base filters
    time_filtered_df = df[(df['alarm_datetime'].dt.date >= start_date) & (df['alarm_datetime'].dt.date <= end_date)]
    if location_type == 'Land Only': time_filtered_df = time_filtered_df[time_filtered_df['on_land']]
    elif location_type == 'Water Only': time_filtered_df = time_filtered_df[~time_filtered_df['on_land']]
    if selected_incident != 'All': time_filtered_df = time_filtered_df[time_filtered_df['Specific Incident Type'] == selected_incident]

    # --- Cascading geographic filters ---
    if not time_filtered_df.empty:
        st.subheader("Geographic Filters")
        dynamic_filters = DynamicFilters(time_filtered_df, filters=['state', 'city'])
        dynamic_filters.display_filters()
        filtered_df = dynamic_filters.filter_df()
    else:
        filtered_df = time_filtered_df
    
    st.metric("Filtered Incidents", f"{len(filtered_df):,}")
    
    # --- Render visuals ---
    col1, col2 = st.columns((2, 1))
    with col1:
        if not filtered_df.empty:
            st.pydeck_chart(pdk.Deck(
                map_style=None,
                initial_view_state=pdk.ViewState(latitude=filtered_df['latitude'].mean(), longitude=filtered_df['longitude'].mean(), zoom=6, pitch=50),
                layers=[pdk.Layer('HexagonLayer', data=filtered_df, get_position='[longitude, latitude]', radius=750, elevation_scale=10, elevation_range=[0, 1000], pickable=True, extruded=True)],
                tooltip={"html": "<b>Incident Count:</b> {elevationValue}"}
            ))
        else:
            st.warning("No data to display on map for the selected filters.")
    with col2:
        st.subheader("Incidents by Hour")
        if not filtered_df.empty:
            st.bar_chart(filtered_df['alarm_datetime'].dt.hour.value_counts().sort_index(), color="#E31C3D")

# =================================================================================================
# TAB 2: CATEGORICAL ANALYSIS (Dashboard 02)
# =================================================================================================
def render_categorical_dashboard(df: pd.DataFrame):
    st.title("Categorical Incident Analysis")
    st.markdown("An analytical view of incident reports, categories, and outcomes.")

    # --- Filters for this tab ---
    filter_cols_cat = st.columns(2)
    with filter_cols_cat[0]:
        categories = sorted(df['incident_category'].unique())
        selected_category = st.selectbox("Select Incident Category", options=categories, key="tab2_category")
    with filter_cols_cat[1]:
        min_date_2 = df['alarm_datetime'].min().date()
        max_date_2 = df['alarm_datetime'].max().date()
        selected_dates = date_range_picker("Select Date Range", default_start=min_date_2, default_end=max_date_2, min_date=min_date_2, max_date=max_date_2, key="tab2_dates")

    start_date, end_date = selected_dates
    time_filtered_df = df[(df['alarm_datetime'].dt.date >= start_date) & (df['alarm_datetime'].dt.date <= end_date)]
    filtered_df = time_filtered_df[time_filtered_df['incident_category'] == selected_category]
    
    if filtered_df.empty:
        st.warning("No incidents found for the selected filters.")
        return

    # --- Render visuals ---
    st.header(f"Key Metrics for: {selected_category}")
    metric_col1, metric_col2 = st.columns(2)
    metric_col1.metric("Total Incidents", f"{len(filtered_df):,}")
    metric_col2.metric("Busiest Day", filtered_df['alarm_datetime'].dt.day_name().value_counts().idxmax())
    st.divider()
    col1, col2 = st.columns(2, gap="large")
    with col1:
        rescues_by_cat = time_filtered_df.groupby('incident_category')['animals_rescued'].sum().reset_index()
        bar_chart = alt.Chart(rescues_by_cat).mark_bar().encode(x=alt.X('incident_category:N', sort='-y', title=None), y=alt.Y('animals_rescued:Q', title="Total Animals Rescued"), color=alt.condition(alt.datum.incident_category == selected_category, alt.value('#E31C3D'), alt.value('#0071BC')))
        st.altair_chart(bar_chart, use_container_width=True, theme="streamlit")
    with col2:
        trends_df = time_filtered_df.groupby([pd.Grouper(key='alarm_datetime', freq='D'), 'incident_category']).size().reset_index(name='count')
        line_chart = alt.Chart(trends_df).mark_line().encode(x=alt.X('alarm_datetime:T', title='Date'), y=alt.Y('count:Q', title='Incidents'), color='incident_category:N', opacity=alt.condition(alt.datum.incident_category == selected_category, alt.value(1.0), alt.value(0.3)))
        st.altair_chart(line_chart, use_container_width=True, theme="streamlit")

# =================================================================================================
# TAB 3: INTERACTIVE GEOSPATIAL ANALYSIS (Dashboard 01/03)
# =================================================================================================
def render_geospatial_dashboard(df: pd.DataFrame):
    st.title("Interactive Geospatial Analysis")
    st.markdown("Explore incident data with an interactive map, chatbot, and detailed analytics.")
    
    # --- Filters for this tab ---
    with st.expander("Show Filters", expanded=True):
        filter_cols_geo = st.columns(4)
        with filter_cols_geo[0]:
            min_date_3, max_date_3 = df['alarm_datetime'].min().date(), df['alarm_datetime'].max().date()
            date_range_map = st.date_input("Date range", value=(min_date_3, max_date_3), min_value=min_date_3, max_value=max_date_3, key="tab3_dates")
        with filter_cols_geo[1]:
            descriptions = sorted(df['incident_description'].unique())
            selected_descs = st.multiselect("Incident Descriptions", descriptions, default=descriptions[:5], key="tab3_descs")
        with filter_cols_geo[2]:
            states = sorted(df['state'].unique())
            selected_state = st.selectbox("State", ["ALL STATES"] + states, key="tab3_state")
        with filter_cols_geo[3]:
            location_type_map = st.radio("Location Type", ('All', 'Land Only', 'Water Only'), key="tab3_location")

    # Filter data
    if len(date_range_map) != 2: return
    start_ts, end_ts = pd.Timestamp(date_range_map[0]).tz_localize("UTC"), pd.Timestamp(date_range_map[1]).tz_localize("UTC") + pd.Timedelta(days=1)
    filtered_df = df[(df['alarm_datetime'] >= start_ts) & (df['alarm_datetime'] < end_ts) & (df['incident_description'].isin(selected_descs))]
    if selected_state != "ALL STATES": filtered_df = filtered_df[filtered_df['state'] == selected_state]
    if location_type_map == 'Land Only': filtered_df = filtered_df[filtered_df['on_land']]
    elif location_type_map == 'Water Only': filtered_df = filtered_df[~filtered_df['on_land']]

    # --- Render visuals ---
    col1, col2 = st.columns([3, 1])
    with col1:
        st.subheader("Incident Map")
        map_config = {}
        if not filtered_df.empty:
            map_config = {'config': {'mapState': {'latitude': filtered_df['latitude'].mean(), 'longitude': filtered_df['longitude'].mean(), 'zoom': 8}}}
        keplergl_static(KeplerGl(height=600, data={"incidents": filtered_df}, config=map_config))
    with col2:
        st.subheader("Summary Stats")
        if not filtered_df.empty:
            st.metric("Total Incidents Found", f"{len(filtered_df):,}")
            st.dataframe(filtered_df['incident_description'].value_counts().head(5).reset_index())
    st.divider()
    col3, col4 = st.columns(2)
    with col3:
        st.subheader("Mission Duration vs. Response Time")
        if not filtered_df.empty and 'mission_duration' in filtered_df.columns:
            scatter = alt.Chart(filtered_df).mark_circle(opacity=0.7).encode(x='mission_duration:Q', y='response_time_minutes:Q', color='incident_description:N', tooltip=['incident_description', 'city', 'mission_duration', 'response_time_minutes'])
            st.altair_chart(scatter, use_container_width=True, theme="streamlit")
    with col4:
        st.subheader("Incident Assistant")
        if "messages" not in st.session_state: st.session_state.messages = [{"role": "assistant", "content": "How can I help?"}]
        for msg in st.session_state.messages:
            st.chat_message(msg["role"]).write(msg["content"])
        if prompt := st.chat_input():
            st.session_state.messages.append({"role": "user", "content": prompt})
            st.chat_message("user").write(prompt)
            st.session_state.messages.append({"role": "assistant", "content": f"Echo: {prompt}"})
            st.chat_message("assistant").write(f"Echo: {prompt}")

# =================================================================================================
# TAB 4: DAILY DEEP-DIVE (Dashboard 04)
# =================================================================================================
def render_daily_analysis_dashboard(df: pd.DataFrame, api_key: str):
    st.title("Daily Incident Deep-Dive")
    st.markdown("Analyze the busiest days and explore potential correlations with weather.")

    st.header("Top 10 Busiest Days by Incident Count")
    daily_counts = df.groupby('date').size().reset_index(name='incident_count')
    top_10_days = daily_counts.sort_values(by='incident_count', ascending=False).head(10)
    top_10_days['formatted_date'] = pd.to_datetime(top_10_days['date']).dt.strftime('%A, %B %d, %Y')
    st.dataframe(top_10_days[['formatted_date', 'incident_count']], use_container_width=True, hide_index=True)
    
    if api_key:
        st.header("Weather Correlation")
        # Placeholder for weather logic - requires running API calls which can be slow
        st.info("Weather correlation analysis would be performed here using the provided API key.")
    
    st.divider()
    selected_day_str = st.selectbox("Select a day to see details:", options=top_10_days['formatted_date'].tolist())
    if selected_day_str:
        day_df = df[df['date'] == pd.to_datetime(selected_day_str).date()]
        st.header(f"Details for: {selected_day_str}")
        st.dataframe(day_df[['alarm_datetime', 'incident_description', 'city', 'state']], use_container_width=True)

# =================================================================================================
# MAIN APP
# =================================================================================================
def main():
    """Main function to orchestrate the multi-tab dashboard."""
    load_css()
    
    with st.sidebar:
        st.image("https://www.usfa.fema.gov/img/logos/neris.svg", width=150)
        st.title("NERIS Dashboard Suite")
        st.divider()
        st.header("Global Settings")
        api_key = st.text_input("OpenWeatherMap API Key", type="password", help="Required for the 'Daily Deep-Dive' tab.")

    try:
        df = load_all_data('data/NERIS_COMPLETE_INCIDENTS.csv')
    except Exception as e:
        st.error(f"🚨 Critical error loading data: {e}")
        return

    tab1, tab2, tab3, tab4 = st.tabs(["3D Density Map", "Categorical Analysis", "Geospatial Analysis", "Daily Deep-Dive"])

    with tab1:
        render_density_map_dashboard(df)
    with tab2:
        render_categorical_dashboard(df)
    with tab3:
        render_geospatial_dashboard(df)
    with tab4:
        render_daily_analysis_dashboard(df, api_key)

if __name__ == "__main__":
    main()


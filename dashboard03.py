import streamlit as st
import pandas as pd
import altair as alt
from keplergl import KeplerGl
from streamlit_keplergl import keplergl_static
from datetime import date
from global_land_mask import globe

# ------------------------
# Streamlit Page Config
# ------------------------
st.set_page_config(
    page_title="NERIS Interactive Map",
    page_icon="🗺️",
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
            /* Main theme colors for light mode */
            :root {
                --primary-bg: #FFFFFF; /* White background */
                --secondary-bg: #F0F2F5; /* Light Gray for sidebar/cards */
                --text-color: #002855; /* NERIS Dark Blue for text */
                --accent-color-red: #E31C3D; /* NERIS Red for highlights */
                --accent-color-blue: #0071BC; /* NERIS Blue */
            }

            /* Apply background to main app and container */
            [data-testid="stAppViewContainer"] {
                background-color: var(--primary-bg);
            }
             .main .block-container, .main {
                background-color: var(--primary-bg);
                color: var(--text-color);
            }

            /* Style sidebar */
            [data-testid="stSidebar"] {
                background-color: var(--secondary-bg);
            }

            /* Style headers */
            h1, h2, h3 {
                color: var(--text-color);
            }

            /* Ensure all text is readable */
             p, .st-emotion-cache-1qg05j4, [data-testid="stMarkdownContainer"] {
                color: var(--text-color);
            }

            /* Style dataframes */
            .stDataFrame {
                border: 1px solid #E0E0E0;
                border-radius: 8px;
            }
        </style>
    """, unsafe_allow_html=True)


# ------------------------
# Load Data
# ------------------------
@st.cache_data
def load_data(path: str) -> pd.DataFrame:
    """
    Loads and cleans the incident dataset, and calculates mission duration.
    """
    df = pd.read_csv(path)

    required_cols = [
        'alarm_datetime', 'last_unit_cleared_datetime', 'response_time_minutes',
        'latitude', 'longitude', 'incident_description', 'city', 'state'
    ]
    df.dropna(subset=required_cols, inplace=True)

    df['alarm_datetime'] = pd.to_datetime(df['alarm_datetime'], errors='coerce', utc=True)
    df['last_unit_cleared_datetime'] = pd.to_datetime(df['last_unit_cleared_datetime'], errors='coerce', utc=True)
    df.dropna(subset=['alarm_datetime', 'last_unit_cleared_datetime'], inplace=True)

    df['latitude'] = pd.to_numeric(df['latitude'], errors='coerce')
    df['longitude'] = pd.to_numeric(df['longitude'], errors='coerce')
    df.dropna(subset=['latitude', 'longitude'], inplace=True)

    df['on_land'] = globe.is_land(df['latitude'], df['longitude'])
    df['mission_duration'] = (df['last_unit_cleared_datetime'] - df['alarm_datetime']).dt.total_seconds() / 60
    df['response_time_minutes'] = pd.to_numeric(df['response_time_minutes'], errors='coerce')
    df.dropna(subset=['response_time_minutes'], inplace=True)

    df = df[df['mission_duration'] > 0]
    df = df[df['response_time_minutes'] > 0]

    df['units_responded'] = pd.to_numeric(df['units_responded'], errors='coerce').fillna(0).astype(int)
    df['patient_status'] = df['patient_status'].fillna('N/A')
    df['fire_suppression_effectiveness'] = df['fire_suppression_effectiveness'].fillna('N/A')

    df.reset_index(drop=True, inplace=True)
    return df


# ------------------------
# Main Application
# ------------------------
def main():
    load_css()
    st.title("NERIS Interactive Incident Map 🗺️")
    st.markdown("Explore incident data using filters. The map updates dynamically based on your selections.")

    try:
        df = load_data('data/NERIS_COMPLETE_INCIDENTS.csv')
        if df.empty:
            st.error("🚨 No data available after cleaning. Please check the source file.")
            return
    except FileNotFoundError:
        st.error("❌ Data file not found. Ensure `NERIS_COMPLETE_INCIDENTS.csv` is in a `data/` folder.")
        return
    except KeyError:
        st.error("🚨 A required column is missing from the data file (e.g., 'response_time_minutes').")
        return

    # Sidebar Filters
    with st.sidebar:
        st.header("Filters")
        min_date = df['alarm_datetime'].min().date()
        max_date = df['alarm_datetime'].max().date()
        date_range = st.date_input("Select date range", value=(min_date, max_date), min_value=min_date,
                                   max_value=max_date)

        if len(date_range) != 2:
            st.warning("Please select a valid date range (start and end date).")
            return

        start_date, end_date = date_range

        incident_descriptions = sorted(df['incident_description'].unique())
        selected_descriptions = st.multiselect("Incident Descriptions", incident_descriptions,
                                               default=incident_descriptions[:5])
        states = sorted(df['state'].unique())
        selected_state = st.selectbox("State", ["ALL STATES"] + states)
        location_type = st.radio("Location Type", ('All', 'Land Only', 'Water Only'))

    # Apply Filters
    start_date_ts = pd.Timestamp(start_date).tz_localize("UTC")
    end_date_ts = pd.Timestamp(end_date).tz_localize("UTC") + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)

    filtered_df = df[
        (df['alarm_datetime'] >= start_date_ts) &
        (df['alarm_datetime'] <= end_date_ts) &
        (df['incident_description'].isin(selected_descriptions))
        ]

    if selected_state != "ALL STATES":
        filtered_df = filtered_df[filtered_df['state'] == selected_state]

    if location_type == 'Land Only':
        filtered_df = filtered_df[filtered_df['on_land']]
    elif location_type == 'Water Only':
        filtered_df = filtered_df[~filtered_df['on_land']]

    # Layout
    col1, col2 = st.columns([3, 1])

    # --- Kepler Map with Dynamic Sizing ---
    with col1:
        st.subheader("Incident Map")

        map_config = {}
        if not filtered_df.empty:
            center_lat = filtered_df['latitude'].mean()
            center_lon = filtered_df['longitude'].mean()

            # This config tells Kepler to size points based on response time
            map_config = {
                'version': 'v1',
                'config': {
                    'mapState': {'latitude': center_lat, 'longitude': center_lon, 'zoom': 8},
                    'visState': {
                        'layers': [{
                            'type': 'point',
                            'config': {
                                'dataId': 'incidents',
                                'label': 'Incidents by Response Time',
                                'color': [227, 28, 61],  # NERIS Red
                                'columns': {'lat': 'latitude', 'lng': 'longitude'},
                                'isVisible': True,
                                'visConfig': {
                                    'radiusRange': [10, 500]  # Set min/max radius in pixels
                                },
                                'visualChannels': {
                                    'sizeField': {'name': 'response_time_minutes', 'type': 'real'},
                                    'sizeScale': 'sqrt'
                                }
                            }
                        }]
                    }
                }
            }

        map_ = KeplerGl(height=600, data={"incidents": filtered_df}, config=map_config)
        keplergl_static(map_)

    # Details Panel
    with col2:
        st.subheader("Summary Stats")
        if filtered_df.empty:
            st.warning("No incidents match the selected filters.")
        else:
            st.metric("Total Incidents Found", f"{len(filtered_df):,}")
            st.write("**Top Incident Descriptions**")
            st.dataframe(filtered_df['incident_description'].value_counts().head(5).reset_index().rename(
                columns={'incident_description': 'Count'}), use_container_width=True)
            st.write("**Top Cities**")
            st.dataframe(filtered_df['city'].value_counts().head(5).reset_index().rename(columns={'city': 'Count'}),
                         use_container_width=True)

    st.divider()

    # Mission Times + Chatbot
    col3, col4 = st.columns(2)

    with col3:
        st.subheader("Mission Duration vs. Response Time")
        if not filtered_df.empty:
            scatter_plot = alt.Chart(filtered_df).mark_circle(size=60, opacity=0.7).encode(
                x=alt.X('mission_duration:Q', title='Total Mission Duration (Minutes)'),
                y=alt.Y('response_time_minutes:Q', title='Initial Response Time (Minutes)'),
                color=alt.Color('incident_description:N', legend=None),
                tooltip=['incident_description', 'city', 'state', 'patient_status', 'mission_duration',
                         'response_time_minutes']
            ).properties(
                title="Mission Duration vs. Response Time"
            ).interactive()
            st.altair_chart(scatter_plot, use_container_width=True, theme="streamlit")
        else:
            st.write("No data to analyze for the scatter plot.")

    with col4:
        st.subheader("Incident Assistant")
        if "messages" not in st.session_state:
            st.session_state.messages = [
                {"role": "assistant", "content": "How can I help you analyze these incidents?"}]
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
        if prompt := st.chat_input("Ask a question about the data..."):
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)
            with st.chat_message("assistant"):
                response = f"Echo: {prompt}"
                st.markdown(response)
            st.session_state.messages.append({"role": "assistant", "content": response})


if __name__ == "__main__":
    main()


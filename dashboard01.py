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

            /* Fix for metric value color */
            [data-testid="stMetricValue"] {
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
# Data Handling
# ------------------------
@st.cache_data
def load_data(path: str) -> pd.DataFrame:
    """
    Loads, cleans, and pre-processes the incident dataset from a CSV file.
    This function is cached to avoid reloading data on every interaction.
    """
    df = pd.read_csv(path)

    required_cols = [
        'alarm_datetime', 'last_unit_cleared_datetime', 'response_time_minutes',
        'latitude', 'longitude', 'incident_description', 'city', 'state'
    ]
    df.dropna(subset=required_cols, inplace=True)

    # Convert datetime columns and handle potential errors
    for col in ['alarm_datetime', 'last_unit_cleared_datetime']:
        df[col] = pd.to_datetime(df[col], errors='coerce', utc=True)
    df.dropna(subset=['alarm_datetime', 'last_unit_cleared_datetime'], inplace=True)

    # Ensure location and response times are numeric
    for col in ['latitude', 'longitude', 'response_time_minutes', 'units_responded']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df.dropna(subset=['latitude', 'longitude', 'response_time_minutes'], inplace=True)

    # Calculate mission duration and filter out invalid data points
    df['mission_duration'] = (df['last_unit_cleared_datetime'] - df['alarm_datetime']).dt.total_seconds() / 60
    df = df[(df['mission_duration'] > 0) & (df['response_time_minutes'] > 0)]

    # Add land/water flag
    df['on_land'] = globe.is_land(df['latitude'], df['longitude'])

    # Fill missing categorical data
    df['patient_status'] = df['patient_status'].fillna('N/A')
    df['fire_suppression_effectiveness'] = df['fire_suppression_effectiveness'].fillna('N/A')
    df['units_responded'] = df['units_responded'].fillna(0).astype(int)

    df.reset_index(drop=True, inplace=True)
    return df


# ------------------------
# UI Component Functions
# ------------------------
def render_sidebar(df: pd.DataFrame) -> dict:
    """Renders the sidebar filters and returns the user's selections."""
    with st.sidebar:
        st.header("Filters")

        min_date = df['alarm_datetime'].min().date()
        max_date = df['alarm_datetime'].max().date()
        date_range = st.date_input("Select date range", value=(min_date, max_date), min_value=min_date,
                                   max_value=max_date)

        incident_descriptions = sorted(df['incident_description'].unique())
        selected_descriptions = st.multiselect("Incident Descriptions", incident_descriptions,
                                               default=incident_descriptions[:5])

        states = sorted(df['state'].unique())
        selected_state = st.selectbox("State", ["ALL STATES"] + states)

        location_type = st.radio("Location Type", ('All', 'Land Only', 'Water Only'))

    return {
        "date_range": date_range,
        "descriptions": selected_descriptions,
        "state": selected_state,
        "location_type": location_type
    }


def render_map(df: pd.DataFrame):
    """Renders the KeplerGL map with dynamic point sizing."""
    st.subheader("Incident Map")

    map_config = {}
    if not df.empty:
        center_lat = df['latitude'].mean()
        center_lon = df['longitude'].mean()
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
                            'color': [227, 28, 61],
                            'columns': {'lat': 'latitude', 'lng': 'longitude'},
                            'isVisible': True,
                            'visConfig': {'radiusRange': [10, 500]},
                            'visualChannels': {
                                'sizeField': {'name': 'response_time_minutes', 'type': 'real'},
                                'sizeScale': 'sqrt'
                            }
                        }
                    }]
                }
            }
        }

    map_ = KeplerGl(height=600, data={"incidents": df}, config=map_config)
    keplergl_static(map_)


def render_summary_panel(df: pd.DataFrame):
    """Renders the summary statistics panel."""
    st.subheader("Summary Stats")
    if df.empty:
        st.warning("No incidents match the selected filters.")
    else:
        st.metric("Total Incidents Found", f"{len(df):,}")
        st.write("**Top Incident Descriptions**")
        st.dataframe(df['incident_description'].value_counts().head(5).reset_index().rename(
            columns={'incident_description': 'Count'}), use_container_width=True)
        st.write("**Top Cities**")
        st.dataframe(df['city'].value_counts().head(5).reset_index().rename(columns={'city': 'Count'}),
                     use_container_width=True)


def render_analysis_charts(df: pd.DataFrame):
    """Renders the mission duration scatterplot and the chatbot."""
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Mission Duration vs. Response Time")
        if not df.empty:
            scatter_plot = alt.Chart(df).mark_circle(size=60, opacity=0.7).encode(
                x=alt.X('mission_duration:Q', title='Total Mission Duration (Minutes)'),
                y=alt.Y('response_time_minutes:Q', title='Initial Response Time (Minutes)'),
                color=alt.Color('incident_description:N', legend=None),
                tooltip=['incident_description', 'city', 'state', 'mission_duration', 'response_time_minutes']
            ).properties(
                title="Mission Duration vs. Response Time"
            ).interactive()
            st.altair_chart(scatter_plot, use_container_width=True, theme="streamlit")
        else:
            st.write("No data to analyze.")

    with col2:
        st.subheader("Incident Assistant")
        if "messages" not in st.session_state:
            st.session_state.messages = [{"role": "assistant", "content": "How can I help?"}]
        for msg in st.session_state.messages:
            st.chat_message(msg["role"]).write(msg["content"])
        if prompt := st.chat_input():
            st.session_state.messages.append({"role": "user", "content": prompt})
            st.chat_message("user").write(prompt)
            response = f"Echo: {prompt}"
            st.session_state.messages.append({"role": "assistant", "content": response})
            st.chat_message("assistant").write(response)


# ------------------------
# Main Application
# ------------------------
def main():
    """Main function to orchestrate the dashboard's creation and logic."""
    load_css()
    st.title("NERIS Interactive Incident Map 🗺️")
    st.markdown("Explore incident data using filters. The map updates dynamically based on your selections.")

    try:
        df = load_data('data/NERIS_COMPLETE_INCIDENTS.csv')
    except (FileNotFoundError, KeyError) as e:
        st.error(f"🚨 Error loading data: {e}")
        return

    filters = render_sidebar(df)
    if len(filters["date_range"]) != 2:
        st.warning("Please select a valid date range.")
        return

    start_date, end_date = filters["date_range"]
    start_ts = pd.Timestamp(start_date).tz_localize("UTC")
    end_ts = pd.Timestamp(end_date).tz_localize("UTC") + pd.Timedelta(days=1)

    # Apply filters
    filtered_df = df[
        (df['alarm_datetime'] >= start_ts) &
        (df['alarm_datetime'] < end_ts) &
        (df['incident_description'].isin(filters["descriptions"]))
        ]
    if filters["state"] != "ALL STATES":
        filtered_df = filtered_df[filtered_df['state'] == filters["state"]]
    if filters["location_type"] == 'Land Only':
        filtered_df = filtered_df[filtered_df['on_land']]
    elif filters["location_type"] == 'Water Only':
        filtered_df = filtered_df[~filtered_df['on_land']]

    # Render main layout
    map_col, summary_col = st.columns([3, 1])
    with map_col:
        render_map(filtered_df)
    with summary_col:
        render_summary_panel(filtered_df)

    st.divider()
    render_analysis_charts(filtered_df)


if __name__ == "__main__":
    main()


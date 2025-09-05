import streamlit as st
import pandas as pd
import pydeck as pdk
from streamlit_dynamic_filters import DynamicFilters
from global_land_mask import globe

st.set_page_config(
    page_title='NERIS 3D Density Map',
    page_icon='🔥',
    layout='wide',
    initial_sidebar_state='expanded')

st.title('🗺️ 3D Map of NERIS Incident Density ️')


@st.cache_data
def load_data(path):
    """
    Loads, cleans, and transforms the dataset.
    - Adds an 'on_land' boolean column.
    - Creates a 'Specific Incident Type' from the last element of 'incident_type'.
    """
    df = pd.read_csv(path)
    original_rows = len(df)

    df['alarm_datetime'] = pd.to_datetime(df['alarm_datetime'], errors='coerce', utc=True)

    df.dropna(subset=['alarm_datetime', 'state', 'city', 'longitude', 'latitude', 'incident_type'], inplace=True)

    parsing_errors = original_rows - len(df)
    if parsing_errors > 0:
        st.warning(f'Found and removed {parsing_errors} rows with invalid/missing data.')

    if not df.empty:
        df['on_land'] = globe.is_land(df['latitude'], df['longitude'])
    else:
        df['on_land'] = pd.Series(dtype=bool)

    if not df.empty:
        df['Specific Incident Type'] = df['incident_type'].str.split('||').str.get(-1)
        df.dropna(subset=['Specific Incident Type'], inplace=True)

    return df


try:
    df = load_data('data/NERIS_COMPLETE_INCIDENTS.csv')

    if df.empty:
        st.error('No valid data to display after cleaning. Please check the source file.')
    else:
        with st.sidebar:
            st.sidebar.image('https://www.usfa.fema.gov/img/logos/neris.svg')
            st.header('🔍 Data Filters')
            st.subheader('Time Filter')
            min_date = df['alarm_datetime'].min().date()
            max_date = df['alarm_datetime'].max().date()
            start_date = st.date_input('Start Date', min_date, min_value=min_date, max_value=max_date)
            end_date = st.date_input('End Date', max_date, min_value=min_date, max_value=max_date)
            if start_date > end_date:
                st.error('Error: End date must be after start date.')

            st.subheader('Location Type')
            location_type = st.radio('Show incidents on:', ('All', 'Land Only', 'Water Only'))

        time_filtered_df = df[
            (df['alarm_datetime'].dt.date >= start_date) & (df['alarm_datetime'].dt.date <= end_date)
            ]
        if location_type == 'Land Only':
            location_filtered_df = time_filtered_df[time_filtered_df['on_land']]
        elif location_type == 'Water Only':
            location_filtered_df = time_filtered_df[~time_filtered_df['on_land']]
        else:
            location_filtered_df = time_filtered_df

        with st.sidebar:
            st.subheader('Incident Filter')
            if not location_filtered_df.empty:
                incident_types = sorted(location_filtered_df['Specific Incident Type'].unique())
                incident_options = ['All'] + incident_types
                selected_incident = st.selectbox('Specific Incident Type', options=incident_options)

                if selected_incident != 'All':
                    incident_filtered_df = location_filtered_df[
                        location_filtered_df['Specific Incident Type'] == selected_incident]
                else:
                    incident_filtered_df = location_filtered_df
            else:
                st.selectbox('Specific Incident Type', options=['No data'], disabled=True)
                incident_filtered_df = location_filtered_df

        if not incident_filtered_df.empty:
            with st.sidebar:
                st.subheader('Geographic Filters')
                dynamic_filters = DynamicFilters(incident_filtered_df, filters=['state', 'city'])
                dynamic_filters.display_filters(location='sidebar')

            filtered_df = dynamic_filters.filter_df()
        else:
            filtered_df = incident_filtered_df

        st.metric('Filtered Incidents', f'{len(filtered_df):,}')

        if not filtered_df.empty:
            st.pydeck_chart(pdk.Deck(
                map_style=None,
                initial_view_state=pdk.ViewState(
                    latitude=filtered_df['latitude'].mean(), longitude=filtered_df['longitude'].mean(), zoom=6,
                    pitch=50,
                ),
                layers=[pdk.Layer(
                    'HexagonLayer', data=filtered_df, get_position='[longitude, latitude]',
                    radius=750, elevation_scale=10, elevation_range=[0, 1000], pickable=True, extruded=True,
                    color_range=[
                        [224, 231, 255, 255],  # Opaque light blue
                        [199, 210, 254, 220],
                        [165, 180, 252, 180],
                        [129, 140, 248, 140],
                        [99, 102, 241, 100],
                        [79, 70, 229, 50],  # Translucent dark indigo
                    ]
                )],
                tooltip={'html': '<b>Incident Count:</b> {elevationValue}'}
            ))
        else:
            st.warning('No data available for the selected filters.')

except FileNotFoundError:
    st.error('Data file not found. Make sure `NERIS_COMPLETE_INCIDENTS.csv` is in a `data/` subfolder.')
except Exception as e:
    st.error(f'An error occurred during data processing: {e}')
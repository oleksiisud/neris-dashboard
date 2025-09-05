import streamlit as st
import pandas as pd
import pydeck as pdk
from streamlit_dynamic_filters import DynamicFilters
from global_land_mask import globe

st.set_page_config(
    page_title='NERIS 3D Geo Dashboard',
    page_icon='🔥',
    layout='wide',
    initial_sidebar_state='expanded'
)


@st.cache_data
def load_data(path):
    '''
    Loads, cleans, and transforms the raw NERIS incident data from a CSV file.

    This function is cached to prevent reloading data on every user interaction.
    It performs the following steps:
    1. Reads the CSV file into a pandas DataFrame.
    2. Converts 'alarm_datetime' to a timezone-aware datetime object.
    3. Drops rows with missing critical data.
    4. Adds a boolean 'on_land' column using global-land-mask.
    5. Extracts the most specific incident type into a new column.
    6. Standardizes the casing for 'state' and 'city' columns.

    Args:
        path (str): The file path to the CSV data.

    Returns:
        pd.DataFrame: The cleaned and transformed DataFrame.
    '''
    df = pd.read_csv(path)
    original_rows = len(df)

    df['alarm_datetime'] = pd.to_datetime(df['alarm_datetime'], errors='coerce', utc=True)
    df.dropna(
        subset=['alarm_datetime', 'state', 'city', 'longitude', 'latitude', 'incident_type'],
        inplace=True
    )

    parsing_errors = original_rows - len(df)
    if parsing_errors > 0:
        st.warning(f'⚠️ Found and removed {parsing_errors} rows with invalid/missing data.')

    if not df.empty:
        df['on_land'] = globe.is_land(df['latitude'], df['longitude'])
        df['Specific Incident Type'] = df['incident_type'].str.split('||').str.get(-1)
        df.dropna(subset=['Specific Incident Type'], inplace=True)
        df['state'] = df['state'].str.upper()
        df['city'] = df['city'].str.title()
    else:
        df['on_land'] = pd.Series(dtype=bool)
        df['Specific Incident Type'] = pd.Series(dtype=str)

    return df


def apply_filters(df, start_date, end_date, location_type, selected_incident):
    '''
    Applies a series of filters to the DataFrame based on user input.
    '''
    filtered = df[
        (df['alarm_datetime'].dt.date >= start_date) &
        (df['alarm_datetime'].dt.date <= end_date)
        ]

    if location_type == 'Land Only':
        filtered = filtered[filtered['on_land']]
    elif location_type == 'Water Only':
        filtered = filtered[~filtered['on_land']]

    if selected_incident != 'All':
        filtered = filtered[filtered['Specific Incident Type'] == selected_incident]

    return filtered


def render_dashboard(df):
    """
    Sets up the Streamlit UI and renders the dashboard components.
    """
    st.title('🗺️ NERIS Incident Density Dashboard ')

    if df.empty:
        st.error('🚨 No valid data to display after cleaning. Please check the source file.')
        return

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

        st.subheader('Map Style')
        transparency_level = st.slider(
            'Transparency Threshold (%)', 0, 100, 0,
            help='Hexagons with incident counts below this percentage of the maximum will be translucent.'
        )

    with st.spinner('Processing data and updating visuals...'):

        base_filtered_df = apply_filters(df, start_date, end_date, location_type, 'All')

        with st.sidebar:
            st.subheader('Incident Filter')
            if not base_filtered_df.empty:
                incident_options = ['All'] + sorted(base_filtered_df['Specific Incident Type'].unique())
                selected_incident = st.selectbox('Specific Incident Type', options=incident_options)
                incident_filtered_df = apply_filters(df, start_date, end_date, location_type, selected_incident)
            else:
                st.selectbox('Specific Incident Type', options=['No data'], disabled=True)
                incident_filtered_df = base_filtered_df

        if not incident_filtered_df.empty:
            with st.sidebar:
                st.subheader('Geographic Filters')
                dynamic_filters = DynamicFilters(incident_filtered_df, filters=['state', 'city'])
                dynamic_filters.display_filters(location='sidebar')
            filtered_df = dynamic_filters.filter_df()
        else:
            filtered_df = incident_filtered_df

        st.metric('Filtered Incidents', f'{len(filtered_df):,}')

        opaque_colors = [
            [224, 231, 255], [199, 210, 254], [165, 180, 252],
            [129, 140, 248], [99, 102, 241], [79, 70, 229],
        ]
        num_translucent = int(len(opaque_colors) * (transparency_level / 100.0))
        dynamic_color_range = [c + [50] if i < num_translucent else c + [255] for i, c in enumerate(opaque_colors)]

        col1, col2 = st.columns((2, 1))
        with col1:
            if not filtered_df.empty:
                st.pydeck_chart(pdk.Deck(
                    map_style=None,
                    initial_view_state=pdk.ViewState(
                        latitude=filtered_df['latitude'].mean(),
                        longitude=filtered_df['longitude'].mean(),
                        zoom=8, pitch=50
                    ),
                    layers=[pdk.Layer(
                        'HexagonLayer', data=filtered_df, get_position='[longitude, latitude]',
                        radius=750, elevation_scale=10, elevation_range=[0, 1000],
                        pickable=True, extruded=True, color_range=dynamic_color_range
                    )],
                    tooltip={'html': '<b>Incident Count:</b> {elevationValue}'}
                ))
            else:
                st.warning('No data available for the selected filters.')

        with col2:
            st.subheader('Incidents by Hour of Day')
            if not filtered_df.empty:
                hourly_counts = filtered_df['alarm_datetime'].dt.hour.value_counts().sort_index()
                st.bar_chart(hourly_counts, color='#ef4444')
            else:
                st.write('No incident data to plot.')


if __name__ == '__main__':
    try:
        initial_df = load_data('data/NERIS_COMPLETE_INCIDENTS.csv')
        render_dashboard(initial_df)
    except FileNotFoundError:
        st.error('❌ Data file not found. Make sure `NERIS_COMPLETE_INCIDENTS.csv` is in a `data/` subfolder.')
    except Exception as e:
        st.error(f'An unexpected error occurred: {e}')
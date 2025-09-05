import streamlit as st
import pandas as pd
import altair as alt
from streamlit_extras.mandatory_date_range import date_range_picker
from datetime import date

st.set_page_config(
    page_title='NERIS Analytics Dashboard v2',
    page_icon='📊',
    layout='wide',
    initial_sidebar_state='expanded'
)
alt.theme.enable('dark')


def load_css():
    """
    Injects custom CSS to style the dashboard with a NERIS-branded dark theme.
    """
    st.markdown('''
        <style>
            :root {
                --primary-bg: #1B2A3E; 
                --secondary-bg: #2C3A4F;
                --text-color: #FFFFFF;
                --accent-color-red: #E31C3D;
                --accent-color-blue: #0071BC;
                --gray-color: #4A5568;
            }
            [data-testid='stAppViewContainer'] {
                background-color: var(--primary-bg);
            }
             .main .block-container, .main {
                background-color: var(--primary-bg);
                color: var(--text-color);
            }
            [data-testid='stSidebar'] {
                background-color: var(--secondary-bg);
            }
            h1, h2, h3 {
                color: var(--text-color);
            }
            [data-testid='stMetric'] {
                background-color: var(--secondary-bg);
                border: 1px solid var(--gray-color);
                border-radius: 10px;
                padding: 1rem;
                text-align: center;
            }
             p, .st-emotion-cache-1qg05j4, [data-testid='stMarkdownContainer'] {
                color: var(--text-color);
            }
        </style>
    ''', unsafe_allow_html=True)


@st.cache_data
def load_data(path):
    """
    Loads, cleans, and transforms the dataset from a CSV file.

    Args:
        path (str): The file path to the CSV data.

    Returns:
        pd.DataFrame: A cleaned and prepared DataFrame for analysis.
    """
    df = pd.read_csv(path)
    original_rows = len(df)
    df['alarm_datetime'] = pd.to_datetime(df['alarm_datetime'], errors='coerce', utc=True)
    df.dropna(subset=['alarm_datetime'], inplace=True)

    fill_unknown_cols = ['state', 'city', 'incident_category', 'incident_type', 'transport_disposition']
    for col in fill_unknown_cols:
        df[col] = df[col].fillna('Unknown')

    df['animals_rescued'] = pd.to_numeric(df['animals_rescued'], errors='coerce').fillna(0).astype(int)
    df['has_smoke_alarm'] = df['has_smoke_alarm'].fillna(False)
    df['has_fire_alarm'] = df['has_fire_alarm'].fillna(False)
    df['has_other_alarm'] = df['has_other_alarm'].fillna(False)
    df['Specific Incident Type'] = df['incident_type'].str.split('||').str.get(-1)
    df['state'] = df['state'].str.upper()
    df['city'] = df['city'].str.title()

    rows_removed = original_rows - len(df)
    if rows_removed > 0:
        st.warning(f'Removed {rows_removed} rows due to invalid date formats.')

    return df


def create_animal_rescue_chart(data, selected_category):
    """
    Creates an Altair bar chart showing the percentage of animals rescued by category.
    """
    rescues_by_category = data.groupby('incident_category')['animals_rescued'].sum().reset_index()
    total_rescued = rescues_by_category['animals_rescued'].sum()
    rescues_by_category['Percentage'] = (
                rescues_by_category['animals_rescued'] / total_rescued * 100) if total_rescued > 0 else 0

    chart = alt.Chart(rescues_by_category).mark_bar().encode(
        x=alt.X('incident_category:N', sort='-y', title=None),
        y=alt.Y('Percentage:Q', title='Percentage of Rescues'),
        color=alt.condition(
            alt.datum.incident_category == selected_category,
            alt.value('#E31C3D'),
            alt.value('#4A5568')
        )
    ).properties(
        title='Percentage of Total Animals Rescued'
    )
    return chart


def create_transport_disposition_chart(data):
    """
    Creates an Altair bar chart for the top 10 transport dispositions.
    """
    disposition_counts = data['transport_disposition'].value_counts().head(10).reset_index()
    chart = alt.Chart(disposition_counts).mark_bar(color='#E31C3D').encode(
        x=alt.X('transport_disposition', sort='-y', title=None),
        y=alt.Y('count', title='Count')
    ).properties(
        title='Top Transport Dispositions'
    )
    return chart


def create_incident_trend_chart(data, selected_category):
    """
    Creates an Altair multi-line chart showing daily incident trends by category.
    """
    trends_df = data.groupby([pd.Grouper(key='alarm_datetime', freq='D'), 'incident_category']).size().reset_index(
        name='count')

    chart = alt.Chart(trends_df).mark_line().encode(
        x=alt.X('alarm_datetime:T', title='Date'),
        y=alt.Y('count:Q', title='Number of Incidents'),
        color=alt.Color('incident_category:N', legend=alt.Legend(title='Category')),
        opacity=alt.condition(
            alt.datum.incident_category == selected_category,
            alt.value(1.0),
            alt.value(0.3)
        ),
        strokeWidth=alt.condition(
            alt.datum.incident_category == selected_category,
            alt.value(4),
            alt.value(2)
        )
    ).properties(
        title='Daily Incident Counts by Category'
    )
    return chart


def main():
    """
    Main function to define the Streamlit application's layout and interactivity.
    """
    load_css()

    try:
        df = load_data('data/NERIS_COMPLETE_INCIDENTS.csv')
        if df.empty:
            st.error('No valid data to display after cleaning.')
            return

        with st.sidebar:
            st.image('https://www.usfa.fema.gov/img/logos/neris.svg')
            st.header('🔍 Data Filters')

            categories = sorted(df['incident_category'].unique())
            selected_category = st.selectbox('Select Incident Category', options=categories)

            min_date = df['alarm_datetime'].min().date()
            max_date = df['alarm_datetime'].max().date()
            selected_dates = date_range_picker(
                'Select Date Range',
                default_start=min_date,
                default_end=max_date,
                min_date=min_date,
                max_date=max_date
            )

        start_date, end_date = selected_dates
        time_filtered_df = df[
            (df['alarm_datetime'].dt.date >= start_date) &
            (df['alarm_datetime'].dt.date <= end_date)
            ]
        category_filtered_df = time_filtered_df[time_filtered_df['incident_category'] == selected_category]

        if category_filtered_df.empty:
            st.warning('No incidents found for the selected category and date range.')
            return

        st.title('📊 NERIS Analytics')
        st.header(f'Key Metrics for: {selected_category}')
        total_incidents = len(category_filtered_df)
        busiest_day = category_filtered_df['alarm_datetime'].dt.day_name().value_counts().idxmax()

        metric_col1, metric_col2 = st.columns(2)
        metric_col1.metric('Total Incidents in Period', f'{total_incidents:,}')
        metric_col2.metric('Busiest Day of the Week', busiest_day)
        st.divider()

        st.header('Detailed Analysis')
        col1, col2 = st.columns(2, gap='large')

        with col1:
            st.subheader('Share of Animals Rescued by Category')
            animal_rescue_chart = create_animal_rescue_chart(time_filtered_df, selected_category)
            st.altair_chart(animal_rescue_chart, use_container_width=True, theme=None)

            if selected_category in ['Structure Fire', 'Other Fire']:
                st.subheader('Fire Alarm Presence')
                alarm_col1, alarm_col2, alarm_col3 = st.columns(3)
                alarm_col1.metric('Smoke Alarms', f'{category_filtered_df['has_smoke_alarm'].mean():.1%}')
                alarm_col2.metric('Fire Alarms', f'{category_filtered_df['has_fire_alarm'].mean():.1%}')
                alarm_col3.metric('Other Alarms', f'{category_filtered_df['has_other_alarm'].mean():.1%}')

            if selected_category == 'Medical':
                st.subheader('Transport Disposition (Top 10)')
                disposition_chart = create_transport_disposition_chart(category_filtered_df)
                st.altair_chart(disposition_chart, use_container_width=True, theme=None)

        with col2:
            st.subheader('Daily Incident Trends by Category')
            incident_trend_chart = create_incident_trend_chart(time_filtered_df, selected_category)
            st.altair_chart(incident_trend_chart, use_container_width=True, theme=None)

    except FileNotFoundError:
        st.error('Data file not found. Make sure `NERIS_COMPLETE_INCIDENTS.csv` is in a `data/` subfolder.')
    except Exception as e:
        st.error(f'An unexpected error occurred: {e}')


if __name__ == '__main__':
    main()


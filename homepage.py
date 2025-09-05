import streamlit as st

st.set_page_config(
    page_title='NERIS Dashboard Suite',
    page_icon='🔥',
    layout='wide'
)

st.title('🔥 Welcome to the NERIS Unified Dashboard Suite')

st.markdown('''
This application combines all the dashboard prototypes built.

**Please use the navigation panel on the left to select a dashboard to view.**

Each page represents a different analytical view of the NERIS incident data:
### **Dashboard 00**
A 3D density map for visualizing incident hotspots.
### **Dashboard 01**
A 3D density map for visualizing incident hotspots with a translucency threshold. 
### **Dashboard 02**
A dashboard focused on categorical analysis and trends.
### **Dashboard 03**
An interactive Kepler map with advanced analytics and a chatbot.
### **Dashboard 04**
A deep-dive analysis of the busiest days with weather correlation.
''')

st.sidebar.image('https://www.usfa.fema.gov/img/logos/neris.svg')
st.sidebar.success('Select a dashboard above.')

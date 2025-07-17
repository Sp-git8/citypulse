import streamlit as st
import geopandas as gpd
import folium
from streamlit_folium import st_folium
import gtfs_kit as gk
from shapely.geometry import Point, LineString

# Read GTFS feed and process the data
feed = gk.read_feed("capmetro", dist_units="km")
stops_df = feed.stops.copy()
transfer_df = feed.transfers.copy()

# Cache transfer data processing to avoid recomputation
@st.cache_data
def process_transfer_data(transfer_df):
    transfer_grouped = (
        transfer_df.groupby("from_stop_id")
        .apply(lambda x: '<ul>' + ''.join(
            f"<li>To Stop {row['to_stop_id']}: {row['min_transfer_time']} seconds</li>"
            for _, row in x.iterrows()
        ) + '</ul>')
        .reset_index(name="transfer_info")
    )
    return transfer_grouped

transfer_grouped = process_transfer_data(transfer_df)

# Merge transfer info into stops dataframe
stops_df = stops_df.merge(transfer_grouped, left_on="stop_id", right_on="from_stop_id", how="left")

# Create geometries for stops and convert to GeoDataFrame
stops_df["geometry"] = stops_df.apply(lambda row: Point(row["stop_lon"], row["stop_lat"]), axis=1)
stops_gdf = gpd.GeoDataFrame(stops_df, geometry="geometry", crs="EPSG:4326")

# Process shapes for route visualization
shapes_df = feed.shapes.sort_values(["shape_id", "shape_pt_sequence"])
shape_geoms = (
    shapes_df.groupby("shape_id")
    .apply(lambda group: LineString(zip(group.shape_pt_lon, group.shape_pt_lat)))
)

shapes_gdf = gpd.GeoDataFrame({"shape_id": shape_geoms.index, "geometry": shape_geoms.values}, crs="EPSG:4326")

# Merge shapes with routes data
trips_routes = feed.trips.merge(feed.routes, on="route_id")
shapes_routes = shapes_gdf.merge(trips_routes, on="shape_id")

# Cache the map initialization to ensure it doesn't reload on every interaction
@st.cache_resource
def create_map():
    m = folium.Map(location=[30.2672, -97.7431], zoom_start=12)
    return m

# Initialize map
m = create_map()

# Add stops to map with popups
for _, row in stops_gdf.iterrows():
    # Create custom circle markers for stops
    folium.CircleMarker(
        location=[row["stop_lat"], row["stop_lon"]],
        radius=5,
        color='blue',
        fill_opacity=0.5,
        fill=True,
    ).add_to(m)
    
    # Add popups to stops with relevant info
    popup_content = f"""
        <b>Stop: {row['stop_name']}</b><br>
        <b>Stop Code:</b> {row['stop_code']}<br>
        <b>Wheelchair Boarding:</b> {'Yes' if row['wheelchair_boarding'] else 'No'}<br>
        <b>Transfer Info:</b><br>{row['transfer_info']}
    """
    folium.Popup(popup_content, max_width=400).add_to(
        folium.Marker([row["stop_lat"], row["stop_lon"]])
    )

# Add routes to the map
folium.GeoJson(
    shapes_gdf,
    popup=folium.GeoJsonPopup(fields=['shape_id']),
    style_function=lambda x: {'color': 'lightblue', 'weight': 3, 'opacity': 0.5}
).add_to(m)

# Streamlit header and map rendering
st.title("Transfer Times Interactive Map with Stops and Labels")
st_data = st_folium(m, width=700, height=500)

# Sidebar for searching stop code
st.sidebar.title("Search Stop Code")
stop_code = st.sidebar.text_input("Enter stop_code")

# Show transfer info if stop_code is entered
if stop_code:
    results = stops_df[stops_df['stop_code'] == stop_code]

    if not results.empty:
        st.sidebar.markdown(f"Transfer Info for `{stop_code}`")
        for _, row in results.iterrows():
            st.sidebar.markdown(row['transfer_info'], unsafe_allow_html=True)
            st.sidebar.markdown("---")
    else:
        st.sidebar.warning("No transfer info found.")

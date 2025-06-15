import configparser
import pandas as pd
import folium
from datetime import datetime, timedelta
import json

config = configparser.ConfigParser()
config.read("config.ini")

LAT = float(config["location"]["lat"])
if not (-90 <= LAT <= 90):
    raise ValueError("Latitude must be between -90 and 90°")
LON = float(config["location"]["lon"])
if not (-180 <= LON <= 180):
    raise ValueError("Longitude must be between -180 and 180°")
RADIUS = float(config["location"]["radius"])
if not (0 < RADIUS <= 250):
    raise ValueError("Longitude must be between 0 and 250 NM")

def parse_timestamp(timestamp_str):
    """Parse timestamp string to datetime object"""
    return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))

def get_altitude_color(altitude, min_alt=0, max_alt=6000):
    """Generate color based on altitude (green=0ft, red=6000ft)"""
    if altitude <= min_alt:
        return '#00FF00'  # Green
    elif altitude >= max_alt:
        return '#FF0000'  # Red
    else:
        # Linear interpolation between green and red
        ratio = (altitude - min_alt) / (max_alt - min_alt)
        red = int(255 * ratio)
        green = int(255 * (1 - ratio))
        return f'#{red:02x}{green:02x}00'

def nautical_miles_to_meters(nm):
    """Convert nautical miles to meters"""
    return nm * 1852  # 1 nautical mile = 1852 meters

def create_aircraft_trajectories(csv_file_path):
    """
    Create aircraft trajectories from CSV data
    Split trajectories when gap > 30 minutes between positions
    """
    # Read CSV data
    df = pd.read_csv(csv_file_path)
    
    # Parse timestamps
    df['datetime'] = df['timestamp'].apply(parse_timestamp)
    
    # Sort by aircraft identifier and timestamp
    df['aircraft_id'] = df['hex']  # Use hex code as unique aircraft identifier
    df = df.sort_values(['aircraft_id', 'datetime'])
    
    trajectories = []
    
    # Process each aircraft
    for aircraft_id in df['aircraft_id'].unique():
        aircraft_data = df[df['aircraft_id'] == aircraft_id].copy()
        
        # Split trajectories based on 30-minute gaps
        current_trajectory = []
        
        for idx, row in aircraft_data.iterrows():
            if current_trajectory:
                # Check time gap with previous point
                time_gap = row['datetime'] - current_trajectory[-1]['datetime']
                
                if time_gap > timedelta(minutes=30):
                    # Save current trajectory and start new one
                    if len(current_trajectory) >= 1:  # Save even single points
                        trajectories.append(current_trajectory.copy())
                    current_trajectory = []
            
            # Add current point to trajectory
            current_trajectory.append({
                'lat': row['lat'],
                'lon': row['lon'],
                'altitude': row['alt'],
                'timestamp': row['timestamp'],
                'callsign': row['callsign'] if pd.notna(row['callsign']) else 'N/A',
                'registration': row['regis'] if pd.notna(row['regis']) else 'N/A',
                'datetime': row['datetime'],
                'aircraft_type': row['type'] if pd.notna(row['type']) else 'N/A'
            })
        
        # Don't forget the last trajectory
        if len(current_trajectory) >= 1:  # Save even single points
            trajectories.append(current_trajectory)
    
    return trajectories

def create_map(trajectories):
    """Create Folium map with aircraft trajectories"""
    # Calculate map center
    all_lats = [point['lat'] for traj in trajectories for point in traj]
    all_lons = [point['lon'] for traj in trajectories for point in traj]
    
    center_lat = sum(all_lats) / len(all_lats)
    center_lon = sum(all_lons) / len(all_lons)
    
    # Create map
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=10,
        tiles='OpenStreetMap'
    )
    
    # Add circle centered on LAT/LON with RADIUS in nautical miles
    radius_meters = nautical_miles_to_meters(RADIUS)
    folium.Circle(
        location=[LAT, LON],
        radius=radius_meters,
        color='black',
        fill=False,
        weight=2,
        opacity=0.8,
        popup=f'Radius: {RADIUS} NM ({radius_meters:.0f} m)'
    ).add_to(m)
    
    # Add center marker
    folium.Marker(
        location=[LAT, LON],
        popup=f'Surveillance point<br>Lat: {LAT}<br>Lon: {LON}',
        icon=folium.Icon(color='black', icon='crosshairs', prefix='fa')
    ).add_to(m)
    
    # Add trajectories to map
    for i, trajectory in enumerate(trajectories):
        if len(trajectory) < 1:  # Skip empty trajectories
            continue
        
        # Handle single point trajectories
        if len(trajectory) == 1:
            point = trajectory[0]
            
            # Create a marker for single point
            popup_content = f"""
            <div style="width: 200px;">
                <b>Single Point {i+1}</b><br>
                <b>Callsign:</b> {point['callsign']}<br>
                <b>Registration:</b> <a href="https://www.flightradar24.com/data/aircraft/{point['registration']}" target="_blank">{point['registration']}</a><br>
                <b>Aircraft Type:</b> {point['aircraft_type']}<br>
                <b>Timestamp:</b> {point['timestamp']}<br>
                <b>Altitude:</b> {point['altitude']} ft<br>
            </div>
            """
            
            # Get color based on altitude
            point_color = get_altitude_color(point['altitude'])
            
            folium.CircleMarker(
                location=[point['lat'], point['lon']],
                radius=8,
                popup=folium.Popup(popup_content, max_width=300),
                color=point_color,
                fill=True,
                fillColor=point_color,
                fillOpacity=0.8
            ).add_to(m)
            
            continue
        
        # Create coordinates for polyline (multiple points)
        coordinates = [[point['lat'], point['lon']] for point in trajectory]
        
        # Get average altitude for color
        avg_altitude = sum(point['altitude'] for point in trajectory) / len(trajectory)
        trajectory_color = get_altitude_color(avg_altitude)
        
        # Create polyline
        polyline = folium.PolyLine(
            coordinates,
            weight=3,
            color=trajectory_color,
            opacity=0.8
        )
        
        # Create popup content with trajectory information
        start_point = trajectory[0]
        end_point = trajectory[-1]
        
        popup_content = f"""
        <div style="width: 200px;">
            <b>Trajectory {i+1}</b><br>
            <b>Callsign:</b> {start_point['callsign']}<br>
            <b>Registration:</b> <a href="https://www.flightradar24.com/data/aircraft/{start_point['registration']}" target="_blank">{start_point['registration']}</a><br>
            <b>Aircraft Type:</b> {start_point['aircraft_type']}<br>
            <b>Start Time:</b> {start_point['timestamp']}<br>
            <b>End Time:</b> {end_point['timestamp']}<br>
            <b>Avg Altitude:</b> {avg_altitude:.0f} ft<br>
            <b>Points:</b> {len(trajectory)}
        </div>
        """
        
        polyline.add_to(m)
        
        # Add popup to the middle of the trajectory
        mid_idx = len(trajectory) // 2
        mid_point = trajectory[mid_idx]
        
        folium.Marker(
            location=[mid_point['lat'], mid_point['lon']],
            popup=folium.Popup(popup_content, max_width=300),
            icon=folium.Icon(color='blue', icon='plane', prefix='fa')
        ).add_to(m)
        
        # Add start and end markers
        folium.CircleMarker(
            location=[trajectory[0]['lat'], trajectory[0]['lon']],
            radius=5,
            popup=f"Start - Alt: {trajectory[0]['altitude']} ft",
            color='green',
            fill=True,
            fillColor='green'
        ).add_to(m)
        
        folium.CircleMarker(
            location=[trajectory[-1]['lat'], trajectory[-1]['lon']],
            radius=5,
            popup=f"End - Alt: {trajectory[-1]['altitude']} ft",
            color='red',
            fill=True,
            fillColor='red'
        ).add_to(m)
    
    # Add legend for altitude colors
    legend_html = '''
    <div style="position: fixed; 
                top: 10px; right: 10px; width: 150px; height: 130px; 
                background-color: white; border:2px solid grey; z-index:9999; 
                font-size:12px; padding: 10px;">
    <p><b>Altitude Legend</b></p>
    <p><i class="fa fa-square" style="color:green"></i> 0 ft</p>
    <p><i class="fa fa-square" style="color:red"></i> 10,000 ft</p>
    <p>Gradient: Low → High</p>
    <hr>
    <p><b>Surveillance area</b></p>
    <p><i class="fa fa-circle-o" style="color:black"></i> ''' + f'{RADIUS} NM' + '''</p>
    </div>
    '''
    m.get_root().html.add_child(folium.Element(legend_html))
    
    return m

def main():
    """Main function to process CSV and create map"""
    # Replace 'your_data.csv' with your actual CSV file path
    csv_file_path = 'records.csv'
    
    try:
        # Create trajectories from CSV data
        print("Processing CSV data...")
        trajectories = create_aircraft_trajectories(csv_file_path)
        print(f"Created {len(trajectories)} trajectories")
        
        # Create map
        print("Creating map...")
        map_object = create_map(trajectories)
        
        # Save map
        output_file = 'aircraft_trajectories_map.html'
        map_object.save(output_file)
        print(f"Map saved as {output_file}")
        print(f"Reference circle: {RADIUS} NM radius centered on ({LAT}, {LON})")
        
        # Print trajectory statistics
        print("\nTrajectory Statistics:")
        for i, traj in enumerate(trajectories):
            print(f"Trajectory {i+1}: {len(traj)} points, "
                  f"Callsign: {traj[0]['callsign']}, "
                  f"Registration: {traj[0]['registration']}")
        
    except FileNotFoundError:
        print(f"Error: CSV file '{csv_file_path}' not found.")
        print("Please make sure the CSV file exists and update the file path in the script.")
    except Exception as e:
        print(f"Error processing data: {str(e)}")

if __name__ == "__main__":
    main()

# Example of how to use with your specific data:
# Save your CSV data as 'aircraft_data.csv' in the same directory as this script
# The script will automatically process it and create 'aircraft_trajectories_map.html'

# CSV Header expected:
# timestamp,callsign,regis,hex,type,desc,alt,vspeed,lat,lon,track,dist,azimuth
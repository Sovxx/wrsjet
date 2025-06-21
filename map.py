import configparser
import pandas as pd
import folium
from datetime import datetime, timedelta
import locale
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
    if pd.isna(altitude) or altitude is None:
        return '#808080'  # Gris pour les valeurs manquantes
    
    altitude = float(altitude)

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

def get_available_dates(csv_file_path):
    """Get list of available dates from CSV data"""
    try:
        df = pd.read_csv(csv_file_path)
        df['datetime'] = df['timestamp'].apply(parse_timestamp)
        df['date'] = df['datetime'].dt.date
        available_dates = sorted(df['date'].unique(), reverse=True)
        return available_dates
    except Exception as e:
        print(f"Error reading dates from CSV: {e}")
        return []

def get_last_detection(csv_file_path):
    """Get the timestamp of the last aircraft detection"""
    try:
        df = pd.read_csv(csv_file_path)
        df['datetime'] = df['timestamp'].apply(parse_timestamp)
        # Get the most recent timestamp
        last_detection = df['datetime'].max()
        return last_detection
    except Exception as e:
        print(f"Error getting last detection: {e}")
        return None

def create_aircraft_trajectories(csv_file_path, selected_date=None):
    """
    Create aircraft trajectories from CSV data
    Split trajectories when gap > 30 minutes between positions
    Filter by date if specified
    """
    # Read CSV data
    df = pd.read_csv(csv_file_path)
    
    # Parse timestamps
    df['datetime'] = df['timestamp'].apply(parse_timestamp)
    df['date'] = df['datetime'].dt.date
    
    # Filter by date if specified
    if selected_date:
        df = df[df['date'] == selected_date]
        if df.empty:
            return []
    
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
                'altitude': row['alt'] if pd.notna(row['alt']) else 0,
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

def create_map_with_filter(csv_file_path):
    """Create Folium map with date filter and aircraft trajectories"""
    # Get available dates
    available_dates = get_available_dates(csv_file_path)
    
    if not available_dates:
        print("No data available")
        return None
    
    # Get last detection timestamp
    last_detection = get_last_detection(csv_file_path)
    
    # Create initial trajectories (all data)
    all_trajectories = create_aircraft_trajectories(csv_file_path)
    
    if not all_trajectories:
        print("No trajectories found")
        return None
    
    # Calculate map center
    all_lats = [point['lat'] for traj in all_trajectories for point in traj]
    all_lons = [point['lon'] for traj in all_trajectories for point in traj]
    
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
    
    # Create JavaScript data for all trajectories grouped by date
    trajectories_by_date = {}
    for date in available_dates:
        date_trajectories = create_aircraft_trajectories(csv_file_path, date)
        trajectories_by_date[str(date)] = date_trajectories
    
    # Convert trajectories to JSON format for JavaScript
    trajectories_json = {}
    for date_str, trajectories in trajectories_by_date.items():
        trajectories_json[date_str] = []
        for traj in trajectories:
            trajectory_data = {
                'points': [{'lat': p['lat'], 'lon': p['lon'], 'altitude': p['altitude'], 
                           'timestamp': p['timestamp'], 'callsign': p['callsign'],
                           'registration': p['registration'], 'aircraft_type': p['aircraft_type']} 
                          for p in traj]
            }
            trajectories_json[date_str].append(trajectory_data)
    
    # Add initial trajectories (first date)
    initial_date = str(available_dates[0])
    add_trajectories_to_map(m, trajectories_by_date[initial_date])
    
    # Create date filter panel
    locale.setlocale(locale.LC_TIME, 'en_US.UTF-8')

    date_options = ''.join([
        f'<option value="{date}">{date.strftime("%A %d/%m/%Y")}</option>' 
        for date in [datetime.strptime(str(d), '%Y-%m-%d').date() for d in available_dates]
    ])
    
    filter_panel_html = f'''
    <div id="date-filter-panel" style="
        position: fixed;
        top: 100px;
        left: 10px;
        width: 220px;
        background-color: white;
        border: 2px solid #ccc;
        border-radius: 8px;
        padding: 15px;
        z-index: 1000;
        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        font-family: Arial, sans-serif;
    ">
        <h4 style="margin-top: 0; margin-bottom: 15px; color: #333;">Filter by Date</h4>
        <div style="margin-bottom: 10px;">
            <label for="date-select" style="display: block; margin-bottom: 5px; font-weight: bold;">
                Select a date:
            </label>
            <select id="date-select" style="
                width: 100%;
                padding: 8px;
                border: 1px solid #ccc;
                border-radius: 4px;
                font-size: 14px;
            ">
                <option value="all">All dates</option>
                {date_options}
            </select>
        </div>
        <div id="flight-count" style="
            font-size: 12px;
            color: #666;
            margin-top: 10px;
            padding: 5px;
            background-color: #f5f5f5;
            border-radius: 4px;
        ">
            Tracks displayed: <span id="count">0</span>
        </div>
    </div>
    '''
    
    # Add JavaScript for filtering
    filter_script = f'''
    <script>
        var trajectoryData = {json.dumps(trajectories_json)};
        var allTrajectoryLayers = [];
        var currentLayers = [];
        
        function getAltitudeColor(altitude) {{
            if (altitude === null || altitude === undefined) return '#808080';
            if (altitude <= 0) return '#00FF00';
            if (altitude >= 6000) return '#FF0000';
            
            var ratio = altitude / 6000;
            var red = Math.floor(255 * ratio);
            var green = Math.floor(255 * (1 - ratio));
            return '#' + red.toString(16).padStart(2, '0') + green.toString(16).padStart(2, '0') + '00';
        }}
        
        function clearTrajectories() {{
            currentLayers.forEach(function(layer) {{
                {m.get_name()}.removeLayer(layer);
            }});
            currentLayers = [];
        }}
        
        function addTrajectoryToMap(trajectory) {{
            var points = trajectory.points;
            if (points.length === 0) return;
            
            if (points.length === 1) {{
                // Single point
                var point = points[0];
                var popup = `
                    <div style="width: 200px;">
                        <b>Point unique</b><br>
                        <b>Callsign:</b> ${{point.callsign}}<br>
                        <b>Registration:</b> <a href="https://www.flightradar24.com/data/aircraft/${{point.registration}}" target="_blank">${{point.registration}}</a><br>
                        <b>Aircraft Type:</b> ${{point.aircraft_type}}<br>
                        <b>Timestamp:</b> ${{point.timestamp}}<br>
                        <b>Altitude:</b> ${{point.altitude}} ft<br>
                    </div>
                `;
                
                var marker = L.circleMarker([point.lat, point.lon], {{
                    radius: 8,
                    color: getAltitudeColor(point.altitude),
                    fill: true,
                    fillColor: getAltitudeColor(point.altitude),
                    fillOpacity: 0.8
                }}).bindPopup(popup);
                
                marker.addTo({m.get_name()});
                currentLayers.push(marker);
                return;
            }}
            
            // Multiple points - create segments
            for (var i = 0; i < points.length - 1; i++) {{
                var startPoint = points[i];
                var endPoint = points[i + 1];
                var avgAltitude = (startPoint.altitude + endPoint.altitude) / 2;
                
                var polyline = L.polyline([
                    [startPoint.lat, startPoint.lon],
                    [endPoint.lat, endPoint.lon]
                ], {{
                    color: getAltitudeColor(avgAltitude),
                    weight: 3,
                    opacity: 0.8
                }});
                
                polyline.addTo({m.get_name()});
                currentLayers.push(polyline);
            }}
            
            // Add trajectory info marker
            var midPoint = points[Math.floor(points.length / 2)];
            var startPoint = points[0];
            var endPoint = points[points.length - 1];
            
            var validAltitudes = points.filter(p => p.altitude !== null && p.altitude !== undefined);
            var avgAltitude = validAltitudes.length > 0 ? 
                validAltitudes.reduce((sum, p) => sum + p.altitude, 0) / validAltitudes.length : 0;
            
            var popup = `
                <div style="width: 200px;">
                    <b>Trajectoire</b><br>
                    <b>Callsign:</b> ${{startPoint.callsign}}<br>
                    <b>Registration:</b> <a href="https://www.flightradar24.com/data/aircraft/${{startPoint.registration}}" target="_blank">${{startPoint.registration}}</a><br>
                    <b>Aircraft Type:</b> ${{startPoint.aircraft_type}}<br>
                    <b>Start Time:</b> ${{startPoint.timestamp}}<br>
                    <b>End Time:</b> ${{endPoint.timestamp}}<br>
                    <b>Avg Altitude:</b> ${{Math.round(avgAltitude)}} ft<br>
                    <b>Points:</b> ${{points.length}}
                </div>
            `;
            
            var infoMarker = L.marker([midPoint.lat, midPoint.lon]).bindPopup(popup);
            
            infoMarker.addTo({m.get_name()});
            currentLayers.push(infoMarker);
            
            // Start marker
            var startMarker = L.circleMarker([startPoint.lat, startPoint.lon], {{
                radius: 5,
                color: 'green',
                fill: true,
                fillColor: 'green'
            }}).bindPopup(`Start - Alt: ${{startPoint.altitude}} ft`);
            
            startMarker.addTo({m.get_name()});
            currentLayers.push(startMarker);
            
            // End marker
            var endMarker = L.circleMarker([endPoint.lat, endPoint.lon], {{
                radius: 5,
                color: 'red',
                fill: true,
                fillColor: 'red'
            }}).bindPopup(`End - Alt: ${{endPoint.altitude}} ft`);
            
            endMarker.addTo({m.get_name()});
            currentLayers.push(endMarker);
        }}
        
        function updateMap(selectedDate) {{
            clearTrajectories();
            
            var trajectoriesToShow = [];
            if (selectedDate === 'all') {{
                // Show all trajectories
                Object.values(trajectoryData).forEach(function(dateTrajectories) {{
                    trajectoriesToShow = trajectoriesToShow.concat(dateTrajectories);
                }});
            }} else {{
                trajectoriesToShow = trajectoryData[selectedDate] || [];
            }}
            
            trajectoriesToShow.forEach(function(trajectory) {{
                addTrajectoryToMap(trajectory);
            }});
            
            // Update counter
            document.getElementById('count').textContent = trajectoriesToShow.length;
        }}
        
        // Initialize
        document.addEventListener('DOMContentLoaded', function() {{
            var dateSelect = document.getElementById('date-select');
            if (dateSelect) {{
                dateSelect.addEventListener('change', function() {{
                    updateMap(this.value);
                }});
                
                // Initialize with first date
                updateMap('{initial_date}');
            }}
        }});
        
        // For maps that load after DOM
        setTimeout(function() {{
            var dateSelect = document.getElementById('date-select');
            if (dateSelect) {{
                dateSelect.addEventListener('change', function() {{
                    updateMap(this.value);
                }});
                updateMap('{initial_date}');
            }}
        }}, 1000);
    </script>
    '''
    
    # Add the filter panel and script to the map
    m.get_root().html.add_child(folium.Element(filter_panel_html))
    m.get_root().html.add_child(folium.Element(filter_script))
    
    # Format last detection timestamp
    last_detection_str = "N/A"
    if last_detection:
        last_detection_str = last_detection.strftime("%d/%m/%Y %H:%M:%S")
    
    # Add legend for altitude colors with last detection
    legend_html = f'''
    <div style="position: fixed; 
                top: 10px; right: 10px; width: 150px; height: 232px; 
                background-color: white; border:2px solid grey; z-index:9999; 
                font-size:12px; padding: 10px;">
    <p><b>Altitude Legend</b></p>
    <p><i class="fa fa-square" style="color:red"></i> 6,000+ ft</p>
    <p><i class="fa fa-square" style="color:green"></i> 0 ft</p>
    <p>Gradient: Low → High</p>
    <p><b>Surveillance area</b></p>
    <p><i class="fa fa-circle-o" style="color:black"></i> {RADIUS} NM</p>
    <p><b>Last detection</b></p>
    <p>{last_detection_str}</p>
    </div>
    '''
    m.get_root().html.add_child(folium.Element(legend_html))
    
    return m

def add_trajectories_to_map(m, trajectories):
    """Helper function to add trajectories to existing map (for initial load)"""
    # This is used for the initial load - the JavaScript will handle updates
    pass

def main(verbose=True):
    """Main function to process CSV and create map with date filter"""
    csv_file_path = 'records.csv'

    try:
        # Create map with date filter
        if verbose:
            print("Processing CSV data and creating interactive map...")
        
        map_object = create_map_with_filter(csv_file_path)
        
        if map_object is None:
            if verbose:
                print("Failed to create map - no data found")
            return
        
        # Save map
        output_file = 'aircraft_trajectories_map_with_filter.html'
        map_object.save(output_file)
        if verbose:
            print(f"Interactive map saved as {output_file}")
            print(f"Reference circle: {RADIUS} NM radius centered on ({LAT}, {LON})")
            print("Use the date filter panel on the left to filter flights by date")
        
    except FileNotFoundError:
        if verbose:
            print(f"Error: CSV file '{csv_file_path}' not found.")
            print("Please make sure the CSV file exists and update the file path in the script.")
    except Exception as e:
        if verbose:
            print(f"Error processing data: {str(e)}")

if __name__ == "__main__":
    main()

# Example of how to use with your specific data:
# Save your CSV data as 'records.csv' in the same directory as this script
# The script will automatically process it and create 'aircraft_trajectories_map_with_filter.html'

# CSV Header expected:
# timestamp,callsign,regis,hex,type,desc,alt,vspeed,lat,lon,track,dist,azimuth
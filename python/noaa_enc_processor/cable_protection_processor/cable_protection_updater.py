######################################################
## FUNCTION TO PROCESS CABLE PROTECTION LAYERS AND  ##
##   UPDATE EXISTING AGOL HOSTED FEATURE SERVICES   ##
######################################################

import io
import zipfile
import requests
import json
import xml.etree.ElementTree as ET
from arcgis.gis import GIS

def update_cable_protection_layer(gis, item_id, geojson_map, gpx_map):
    all_esri_points = []

    # 1. Download and process GeoJSON zipped files
    for url, project_name in geojson_map.items():
        print(f"Downloading GeoJSON: {url} for Project: {project_name}")
        response = requests.get(url)
        if response.status_code != 200:
            print(f"Failed to download {url}")
            continue
            
        with zipfile.ZipFile(io.BytesIO(response.content)) as z:
            for filename in z.namelist():
                if filename.endswith('.geojson'):
                    with z.open(filename) as f:
                        try:
                            gj_data = json.load(f)
                            for feat in gj_data['features']:
                                # Skip features missing structural geometry
                                if not feat.get('geometry') or not feat['geometry'].get('coordinates'):
                                    continue
                                    
                                geom_type = feat['geometry']['type']
                                
                                # --- FILTER OUT EVERYTHING EXCEPT POINTS ---
                                if geom_type != 'Point':
                                    # Silently ignore polygons and lines completely
                                    continue
                                    
                                props = feat['properties']
                                coords = feat['geometry']['coordinates']
                                
                                point_feat = {
                                    "attributes": {
                                        "Protection_ID": props.get('name') or props.get('id'),
                                        "Information": props.get('description') or props.get('type'),
                                        "Project": project_name
                                    },
                                    "geometry": {
                                        "x": coords[0],
                                        "y": coords[1],
                                        "spatialReference": {"wkid": 4326}
                                    }
                                }
                                all_esri_points.append(point_feat)
                                    
                        except Exception as e:
                            print(f"Error parsing GeoJSON feature in {filename}: {e}")

    # 2. Download and process GPX zipped files 
    for url, project_name in gpx_map.items():
        print(f"Downloading GPX Points: {url} for Project: {project_name}")
        response = requests.get(url)
        if response.status_code != 200:
            print(f"Failed to download {url}")
            continue
            
        with zipfile.ZipFile(io.BytesIO(response.content)) as z:
            for filename in z.namelist():
                if filename.endswith('.gpx'):
                    with z.open(filename) as f:
                        try:
                            tree = ET.parse(f)
                            root = tree.getroot()
                            ns = {'gpx': root.tag.split('}')[0].strip('{')} if '}' in root.tag else {'gpx': ''}
                            prefix = 'gpx:' if ns['gpx'] else ''
                            
                            # Query ONLY waypoints (<wpt>)
                            waypoints = root.findall(f'.//{prefix}wpt', ns)
                            for wpt in waypoints:
                                try:
                                    lon = float(wpt.get('lon'))
                                    lat = float(wpt.get('lat'))
                                    name_el = wpt.find(f'{prefix}name', ns)
                                    desc_el = wpt.find(f'{prefix}desc', ns)
                                    
                                    point_feat = {
                                        "attributes": {
                                            "Protection_ID": name_el.text if name_el is not None else "GPX-WPT",
                                            "Information": desc_el.text if desc_el is not None else "Waypoint location",
                                            "Project": project_name
                                        },
                                        "geometry": {
                                            "x": lon,
                                            "y": lat,
                                            "spatialReference": {"wkid": 4326}
                                        }
                                    }
                                    all_esri_points.append(point_feat)
                                except (ValueError, TypeError):
                                    continue
                        except Exception as e:
                            print(f"Error decoding GPX Point structure in {filename}: {e}")

    # ====================================================
    # AGOL UPLOAD LOGIC
    # ====================================================
    if not all_esri_points:
        print("No point features discovered to upload.")
        return

    target_item = gis.content.get(item_id)
    if not target_item:
        print(f"Error: Could not retrieve AGOL Item ID: {item_id}")
        return
        
    # Targets the single main layer (index 0)
    flayer = target_item.layers[0]

    target_fields = [
        {"name": "Protection_ID", "type": "esriFieldTypeString", "alias": "Protection ID", "nullable": True},
        {"name": "Information", "type": "esriFieldTypeString", "alias": "Information", "nullable": True},
        {"name": "Project", "type": "esriFieldTypeString", "alias": "Project", "nullable": True} 
    ]

    if not flayer.properties.fields:
        print(f"Initializing layer schema constraints for layer: {flayer.properties.name}...")
        flayer.manager.add_to_definition({"fields": target_fields})

    allowed_keys = [f['name'] for f in target_fields]
    cleaned_features = []
    for feat in all_esri_points:
        filtered_attributes = {k: v for k, v in feat['attributes'].items() if k in allowed_keys}
        feat['attributes'] = filtered_attributes
        cleaned_features.append(feat)

    try:
        current_count = flayer.query(where="1=1", return_count_only=True)
        if current_count > 0:
            print(f"Found {current_count} existing features in layer '{flayer.properties.name}'. Clearing layer...")
            flayer.delete_features(where="1=1")
    except Exception:
        pass

    print(f"Pushing {len(cleaned_features)} point features to layer: '{flayer.properties.name}'...")
    for i in range(0, len(cleaned_features), 1000):
        chunk = cleaned_features[i:i + 1000]
        result = flayer.edit_features(adds=chunk)
        if 'addResults' in result:
            fails = [r for r in result['addResults'] if not r['success']]
            if fails:
                print(f"Batch {(i//1000)+1} had {len(fails)} faults on layer '{flayer.properties.name}'. Error: {fails[0].get('error')}")

    print("Sync complete.")
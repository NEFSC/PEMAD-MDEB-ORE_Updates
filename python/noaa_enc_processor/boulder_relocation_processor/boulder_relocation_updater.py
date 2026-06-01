######################################################
## FUNCTION TO PROCESS BOULDER RELOCATION FILES AND ##
##   UPDATE EXISTING AGOL HOSTED FEATURE SERVICES   ##
######################################################

import io
import zipfile
import requests
import json
import csv
import xml.etree.ElementTree as ET # --- XML parser for GPX payload
from arcgis.gis import GIS

def update_boulder_layer(gis, item_id, geojson_map, gpx_project_map=None, csv_path=None):
    all_esri_features = []

    # Download and process GeoJSON files
    for url, project_name in geojson_map.items():
        print(f"Downloading: {url} for Project: {project_name}")
        
        response = requests.get(url)
        if response.status_code != 200:
            print(f"Failed to download {url}")
            continue
            
        with zipfile.ZipFile(io.BytesIO(response.content)) as z:
            for filename in z.namelist():
                if filename.endswith('.geojson'):
                    with z.open(filename) as f:
                        gj_data = json.load(f)
                        
                        # Convert GeoJSON Feature to Esri Feature format
                        for feat in gj_data['features']:
                            
                            props = feat['properties']
                            # Map GeoJSON column name to AGOL column name
                            formatted_props = {
                                "Boulder_ID": props.get('name'),
                                "Information": props.get('description'),
                                "Project": project_name
                            }
            
                            esri_feat = {
                                "attributes": formatted_props,
                                "geometry": {
                                    "x": feat['geometry']['coordinates'][0],
                                    "y": feat['geometry']['coordinates'][1],
                                    "spatialReference": {"wkid": 4326}
                                }
                            }
                            all_esri_features.append(esri_feat) 

    # Download and process remote GPX zip files
    # Using GPX because this Quintham plotter file didn't have a GeoJSON option
    if gpx_project_map:
        for url, project_name in gpx_project_map.items():
            print(f"Downloading GPX: {url} for Project: {project_name}")
            
            response = requests.get(url)
            if response.status_code != 200:
                print(f"Failed to download {url}")
                continue
                
            with zipfile.ZipFile(io.BytesIO(response.content)) as z:
                for filename in z.namelist():
                    if filename.endswith('.gpx'):
                        with z.open(filename) as f:
                            try:
                                # Parse XML 
                                tree = ET.parse(f)
                                root = tree.getroot()
                                
                                # Dynamic handling of GPX XML namespaces
                                ns = {'gpx': root.tag.split('}')[0].strip('{')} if '}' in root.tag else {'gpx': ''}
                                prefix = 'gpx:' if ns['gpx'] else ''
                                
                                # Query for <wpt> (waypoints). If Quintham tracks them as tracks/routes,
                                # use f'.//{prefix}trkpt' instead.
                                waypoints = root.findall(f'.//{prefix}wpt', ns)
                                
                                for wpt in waypoints:
                                    try:
                                        lon = float(wpt.get('lon'))
                                        lat = float(wpt.get('lat'))
                                        
                                        name_el = wpt.find(f'{prefix}name', ns)
                                        desc_el = wpt.find(f'{prefix}desc', ns)
                                        
                                        boulder_id = name_el.text if name_el is not None else None
                                        information = desc_el.text if desc_el is not None else None
                                        
                                        gpx_feat = {
                                            "attributes": {
                                                "Boulder_ID": boulder_id,
                                                "Information": information,
                                                "Project": project_name
                                            },
                                            "geometry": {
                                                "x": lon,
                                                "y": lat,
                                                "spatialReference": {"wkid": 4326}
                                            }
                                        }
                                        all_esri_features.append(gpx_feat)
                                    except (ValueError, TypeError):
                                        continue
                            except Exception as e:
                                print(f"Error parsing GPX file {filename}: {e}")

    # Process csv file of Empire Wind boulder locations
    if csv_path and csv_path.exists():
        print(f"Processing CSV file: {csv_path}")
        with open(csv_path, mode='r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    # Creating the feature structure to match the AGOL schema
                    csv_feat = {
                        "attributes": {
                            "Boulder_ID": row.get('Boulder_ID'),
                            "Information": row.get('Information'),
                            "Project": row.get('Project')
                        },
                        "geometry": {
                            "x": float(row.get('Lon')),
                            "y": float(row.get('Lat')),
                            "spatialReference": {"wkid": 4326}
                        }
                    }
                    all_esri_features.append(csv_feat)
                except (ValueError, TypeError) as e:
                    print(f"Skipping CSV row {row.get('Boulder_ID')} due to invalid coordinates.")
    else:
        print(f"Note: No CSV file found or processed at {csv_path}")

    # Upload to AGOL
    if not all_esri_features:
        print("No features found.")
        return

    # Schema initalization 
    target_item = gis.content.get(item_id)
    flayer = target_item.layers[0]

    # 1. Define the columns to keep
    target_fields = [
        {"name": "Boulder_ID", "type": "esriFieldTypeString", "alias": "Boulder ID", "nullable": True},
        {"name": "Information", "type": "esriFieldTypeString", "alias": "Information", "nullable": True},
        {"name": "Project", "type": "esriFieldTypeString", "alias": "Project", "nullable": True} 
    ]

    # 2. Check if the layer is currently empty of fields
    if not flayer.properties.fields:
        print("Initializing layer schema...")
        flayer.manager.add_to_definition({
            "fields": target_fields
        })

    # 3. Filter features to ONLY include these attributes
    allowed_keys = [f['name'] for f in target_fields]
    
    cleaned_features = []
    for feat in all_esri_features:
        # Create a new attribute dict containing only allowed keys
        filtered_attributes = {k: v for k, v in feat['attributes'].items() if k in allowed_keys}
        feat['attributes'] = filtered_attributes
        cleaned_features.append(feat)

    # Conditional Delete: Only if records exist
    try:
        current_count = flayer.query(where="1=1", return_count_only=True)
        if current_count > 0:
            print(f"Found {current_count} existing features. Clearing layer...")
            flayer.delete_features(where="1=1")
        else:
            print("Layer is already empty. Skipping delete step.")
    except Exception:
        # If the layer is so new it has no table yet, query might fail
        print("Layer schema not yet initialized. Skipping delete step.")

    # UPLOAD: Push in batches of 1000 to avoid timeout/size errors
    print(f"Pushing {len(cleaned_features)} features to: {target_item.title}...")
    
    for i in range(0, len(cleaned_features), 1000):
        chunk = cleaned_features[i:i + 1000]
        result = flayer.edit_features(adds=chunk)
        
        # Check for errors in the batch
        if 'addResults' in result:
            fails = [r for r in result['addResults'] if not r['success']]
            if fails:
                print(f"Batch {(i//1000)+1} had {len(fails)} failures. Error: {fails[0].get('error')}")

    print("Sync complete.")
    print("Update complete.")
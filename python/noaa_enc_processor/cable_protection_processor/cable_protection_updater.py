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

def update_cable_protection_layer(gis, item_id, geojson_map, gpx_map, point_idx=0, poly_idx=1):
    # Separate data buckets based on geometry type
    all_esri_lines_polys = []
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
                                props = feat['properties']
                                
                                formatted_props = {
                                    "Protection_ID": props.get('name') or props.get('id'),
                                    "Information": props.get('description') or props.get('type'),
                                    "Project": project_name
                                }
                                
                                geom_type = feat['geometry']['type']
                                coords = feat['geometry']['coordinates']
                                esri_geometry = {"spatialReference": {"wkid": 4326}}
                                is_point = False
                                
                                if geom_type == 'LineString':
                                    esri_geometry['paths'] = [coords]
                                elif geom_type == 'MultiLineString':
                                    esri_geometry['paths'] = coords if isinstance(coords[0][0], list) else [coords]
                                # --- REFACTORED POLYGON VALIDATION LOGIC ---
                                elif geom_type == 'Polygon':
                                    # Ensure the structure is wrapped correctly as a list of rings
                                    # Expected: [[ [lon1,lat1], [lon2,lat2], ... ]]
                                    rings = coords if isinstance(coords[0][0], (int, float)) == False else [coords]
                                    
                                    # FIX WINDING ORDER: Force outer ring to Clockwise
                                    fixed_rings = []
                                    for ring in rings:
                                        if len(ring) >= 3:
                                            # Shoelace Formula to calculate orientation area
                                            area = 0.0
                                            for i in range(len(ring) - 1):
                                                area += (ring[i][0] * ring[i+1][1]) - (ring[i+1][0] * ring[i][1])
                                            
                                            # area > 0 means Counter-Clockwise (OGC standard)
                                            # Esri needs outer rings to be Clockwise (area < 0)
                                            if area > 0:
                                                print(f"Warning: Counter-Clockwise ring detected in {filename}. Reversing vertices for AGOL layout.")
                                                ring = ring[::-1] # Reverse the coordinate points array
                                        fixed_rings.append(ring)
                                        
                                    esri_geometry['rings'] = fixed_rings

                                elif geom_type == 'MultiPolygon':
                                    flat_rings = []
                                    # Extract nested geometry layers out to an Esri flat ring set
                                    for poly in coords:
                                        for ring in poly:
                                            if len(ring) >= 3:
                                                # Fix winding order for MultiPolygon components as well
                                                area = 0.0
                                                for i in range(len(ring) - 1):
                                                    area += (ring[i][0] * ring[i+1][1]) - (ring[i+1][0] * ring[i][1])
                                                if area > 0:
                                                    ring = ring[::-1]
                                            flat_rings.append(ring)
                                            
                                    esri_geometry['rings'] = flat_rings
                                elif geom_type == 'Point':
                                    esri_geometry['x'] = coords[0]
                                    esri_geometry['y'] = coords[1]
                                    is_point = True
                                    
                                esri_feat = {
                                    "attributes": formatted_props,
                                    "geometry": esri_geometry
                                }
                                
                                if is_point:
                                    all_esri_points.append(esri_feat)
                                else:
                                    all_esri_lines_polys.append(esri_feat)
                                    
                        except Exception as e:
                            print(f"Error parsing GeoJSON feature in {filename}: {e}")

    # 2. Download and process gpx zipped files
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
                            
                            # Extract dynamic GPX namespace schemas
                            ns = {'gpx': root.tag.split('}')[0].strip('{')} if '}' in root.tag else {'gpx': ''}
                            prefix = 'gpx:' if ns['gpx'] else ''
                            
                            # Strictly query for waypoints (<wpt>)
                            waypoints = root.findall(f'.//{prefix}wpt', ns)
                            print(f"Found {len(waypoints)} waypoint nodes in {filename}")
                            
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
                                    # Route 100% of these features into the point bucket
                                    all_esri_points.append(point_feat)
                                except (ValueError, TypeError):
                                    continue
                                    
                        except Exception as e:
                            print(f"Error decoding GPX Point structure in {filename}: {e}")

    # ====================================================
    # HELPER FUNCTION FOR SUB-LAYER UPLOADS
    # ====================================================
    def upload_to_sublayer(target_item, layer_index, features, description_label):
        if not features:
            print(f"No {description_label} features discovered to upload.")
            return

        # Target the specific sub-layer inside the service item using index numbers
        try:
            flayer = target_item.layers[layer_index]
        except IndexError:
            print(f"Error: Sub-layer index {layer_index} does not exist in feature service '{target_item.title}'")
            return

        target_fields = [
            {"name": "Protection_ID", "type": "esriFieldTypeString", "alias": "Protection ID", "nullable": True},
            {"name": "Information", "type": "esriFieldTypeString", "alias": "Information", "nullable": True},
            {"name": "Project", "type": "esriFieldTypeString", "alias": "Project", "nullable": True} 
        ]

        if not flayer.properties.fields:
            print(f"Initializing layer schema constraints for sub-layer: {flayer.properties.name}...")
            flayer.manager.add_to_definition({"fields": target_fields})

        allowed_keys = [f['name'] for f in target_fields]
        cleaned_features = []
        for feat in features:
            filtered_attributes = {k: v for k, v in feat['attributes'].items() if k in allowed_keys}
            feat['attributes'] = filtered_attributes
            cleaned_features.append(feat)

        try:
            current_count = flayer.query(where="1=1", return_count_only=True)
            if current_count > 0:
                print(f"Found {current_count} existing features in sub-layer '{flayer.properties.name}'. Clearing layer...")
                flayer.delete_features(where="1=1")
        except Exception:
            pass

        print(f"Pushing {len(cleaned_features)} features to sub-layer: '{flayer.properties.name}'...")
        for i in range(0, len(cleaned_features), 1000):
            chunk = cleaned_features[i:i + 1000]
            result = flayer.edit_features(adds=chunk)
            if 'addResults' in result:
                fails = [r for r in result['addResults'] if not r['success']]
                if fails:
                    print(f"Batch {(i//1000)+1} had {len(fails)} faults on sub-layer '{flayer.properties.name}'. Error: {fails[0].get('error')}")


    # Fetch the main service item once
    target_service_item = gis.content.get(item_id)
    if not target_service_item:
        print(f"Error: Could not retrieve AGOL Item ID: {item_id}")
        return

    # Run the upload cycle for both sub-layers independently
    print(f"\nTargeting Feature Service: {target_service_item.title}")
    
    print("\n--- Processing Lines/Polygons Sub-Layer ---")
    upload_to_sublayer(target_service_item, poly_idx, all_esri_lines_polys, "Lines/Polygons")
    
    print("\n--- Processing Points Sub-Layer ---")
    upload_to_sublayer(target_service_item, point_idx, all_esri_points, "Points")

    print("\nSync complete.")
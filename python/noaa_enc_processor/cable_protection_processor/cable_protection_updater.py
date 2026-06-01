######################################################
## FUNCTION TO PROCESS CABLE PROTECTION LAYERS AND  ##
##   UPDATE EXISTING AGOL HOSTED FEATURE SERVICES   ##
######################################################

import io
import zipfile
import requests
import json
import shapefile  
from arcgis.gis import GIS

def update_cable_protection_layer(gis, item_id, geojson_map, shapefile_map, point_idx=0, poly_idx=1):
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
                                elif geom_type == 'Polygon':
                                    esri_geometry['rings'] = coords
                                elif geom_type == 'MultiPolygon':
                                    flat_rings = []
                                    for poly in coords:
                                        for ring in poly:
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

    # 2. Download and process Shapefile zipped files
    for url, project_name in shapefile_map.items():
        print(f"Downloading Shapefile: {url} for Project: {project_name}")
        response = requests.get(url)
        if response.status_code != 200:
            print(f"Failed to download {url}")
            continue
            
        with zipfile.ZipFile(io.BytesIO(response.content)) as z:
            shp_file = next((io.BytesIO(z.read(f)) for f in z.namelist() if f.endswith('.shp')), None)
            shx_file = next((io.BytesIO(z.read(f)) for f in z.namelist() if f.endswith('.shx')), None)
            dbf_file = next((io.BytesIO(z.read(f)) for f in z.namelist() if f.endswith('.dbf')), None)
            
            if not shp_file or not dbf_file:
                print(f"Incomplete shapefile contents inside zip for {url}")
                continue
                
            try:
                with shapefile.Reader(shp=shp_file, shx=shx_file, dbf=dbf_file) as sf:
                    fields = [f[0].lower() for f in sf.fields[1:]] 
                    
                    for shape_record in sf.shapeRecords():
                        shape = shape_record.shape
                        record_dict = dict(zip(fields, shape_record.record))
                        
                        formatted_props = {
                            "Protection_ID": str(record_dict.get('name') or record_dict.get('id', '')),
                            "Information": str(record_dict.get('desc') or record_dict.get('type', '')),
                            "Project": project_name
                        }
                        
                        esri_geometry = {"spatialReference": {"wkid": 4326}}
                        is_point = False
                        
                        if shape.shapeType in [3, 13, 23]: 
                            parts = shape.parts
                            points = shape.points
                            paths = []
                            for idx in range(len(parts)):
                                start = parts[idx]
                                end = parts[idx+1] if idx+1 < len(parts) else len(points)
                                paths.append(points[start:end])
                            esri_geometry['paths'] = paths
                            
                        elif shape.shapeType in [5, 15, 25]: 
                            parts = shape.parts
                            points = shape.points
                            rings = []
                            for idx in range(len(parts)):
                                start = parts[idx]
                                end = parts[idx+1] if idx+1 < len(parts) else len(points)
                                rings.append(points[start:end])
                            esri_geometry['rings'] = rings
                            
                        elif shape.shapeType in [1, 11, 21]: 
                            esri_geometry['x'] = shape.points[0][0]
                            esri_geometry['y'] = shape.points[0][1]
                            is_point = True
                            
                        esri_feat = {
                            "attributes": {
                                "Protection_ID": str(record_dict.get('name') or record_dict.get('id', '')),
                                "Information": str(record_dict.get('desc') or record_dict.get('type', '')),
                                "Project": project_name
                            },
                            "geometry": esri_geometry
                        }
                        
                        if is_point:
                            all_esri_points.append(esri_feat)
                        else:
                            all_esri_lines_polys.append(esri_feat)
                            
            except Exception as e:
                print(f"Error decoding Shapefile structure: {e}")


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
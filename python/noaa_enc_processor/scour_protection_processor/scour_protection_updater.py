######################################################
## FUNCTION TO PROCESS SCOUR PROTECTION LAYERS AND  ##
##   UPDATE EXISTING AGOL HOSTED FEATURE SERVICES   ##
######################################################

import io
import zipfile
import requests
import json
from arcgis.gis import GIS
from shapely.geometry import shape
from shapely.ops import orient

def update_scour_protection_layer(gis, item_id, geojson_map, point_idx=0, poly_idx=1):
    # Separate data buckets based on incoming geometry type
    all_esri_points = []
    all_esri_polygons = []

    # 1. Download and process GeoJSON zipped files
    for url, project_name in geojson_map.items():
        print(f"Downloading Scour GeoJSON: {url} for Project: {project_name}")
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
                                if not feat.get('geometry') or not feat['geometry'].get('coordinates'):
                                    continue
                                    
                                props = feat['properties']
                                formatted_props = {
                                    "Scour_ID": props.get('name') or props.get('id'),
                                    "Information": props.get('description') or props.get('type'),
                                    "Project": project_name
                                }
                                
                                geom_type = feat['geometry']['type']
                                coords = feat['geometry']['coordinates']
                                esri_geometry = {"spatialReference": {"wkid": 4326}}
                                is_point = False
                                
                                # A. Process Point Features (Sunrise Wind data)
                                if geom_type == 'Point':
                                    esri_geometry['x'] = coords[0]
                                    esri_geometry['y'] = coords[1]
                                    is_point = True
                                    
                                # B. Process Polygon Rings (Vineyard Wind 1 data)
                                elif geom_type in ['Polygon', 'MultiPolygon']:
                                    try:
                                        raw_poly = shape(feat['geometry'])
                                        
                                        # Repair open loops or self-intersections
                                        if not raw_poly.is_valid:
                                            raw_poly = raw_poly.buffer(0)
                                            
                                        polygons_to_process = [raw_poly] if geom_type == 'Polygon' else list(raw_poly.geoms)
                                        
                                        esri_rings = []
                                        for poly in polygons_to_process:
                                            # Force Clockwise vertex mapping required by Esri to draw on maps
                                            esri_compliant_poly = orient(poly, sign=-1)
                                            if not esri_compliant_poly.exterior:
                                                continue
                                            esri_rings.append(list(esri_compliant_poly.exterior.coords))
                                            for interior in esri_compliant_poly.interiors:
                                                esri_rings.append(list(interior.coords))
                                                
                                        if not esri_rings or not esri_rings[0]:
                                            continue
                                            
                                        esri_geometry['rings'] = esri_rings
                                        
                                    except Exception as shapely_err:
                                        print(f"Warning: Skipping invalid polygon segment in {filename}: {shapely_err}")
                                        continue 
                                else:
                                    # Ignore any other unexpected geometry class type
                                    continue

                                esri_feat = {
                                    "attributes": formatted_props,
                                    "geometry": esri_geometry
                                }
                                
                                # Route feature into correct bucket based on geometry
                                if is_point:
                                    all_esri_points.append(esri_feat)
                                else:
                                    all_esri_polygons.append(esri_feat)
                                    
                        except Exception as e:
                            print(f"Error parsing Scour GeoJSON feature in {filename}: {e}")
                

    # ====================================================
    # HELPER FUNCTION FOR SUB-LAYER UPLOADS
    # ====================================================
    def upload_to_sublayer(target_item, layer_index, features, description_label):
        if not features:
            print(f"No {description_label} features discovered to upload.")
            return

        try:
            flayer = target_item.layers[layer_index]
        except IndexError:
            print(f"Error: Sub-layer index {layer_index} does not exist in feature service '{target_item.title}'")
            return

        target_fields = [
            {"name": "Scour_ID", "type": "esriFieldTypeString", "alias": "Scour ID", "nullable": True},
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

    print(f"\nTargeting Feature Service: {target_service_item.title}")
    
    print("\n--- Processing Points Sub-Layer (0) ---")
    upload_to_sublayer(target_service_item, point_idx, all_esri_points, "Points")
    
    print("\n--- Processing Polygons Sub-Layer (1) ---")
    upload_to_sublayer(target_service_item, poly_idx, all_esri_polygons, "Polygons")

    print("\nSync complete.")

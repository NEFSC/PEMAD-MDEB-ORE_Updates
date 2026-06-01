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

def update_cable_protection_layer(gis, item_id, geojson_map, shapefile_map):
    all_esri_features = []

    # Download and process GeoJSON zipped files
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
                                
                                # Uniformly map properties to AGOL fields
                                formatted_props = {
                                    "Protection_ID": props.get('name') or props.get('id'),
                                    "Information": props.get('description') or props.get('type'),
                                    "Project": project_name
                                }
                                
                                # Dynamic Esri Geometry handling (Point, Line, or Polygon)
                                geom_type = feat['geometry']['type']
                                coords = feat['geometry']['coordinates']
                                esri_geometry = {"spatialReference": {"wkid": 4326}}
                                
                                if geom_type in ['LineString', 'MultiLineString']:
                                    esri_geometry['paths'] = coords if geom_type == 'MultiLineString' else [coords]
                                elif geom_type in ['Polygon', 'MultiPolygon']:
                                    esri_geometry['rings'] = coords if geom_type == 'MultiPolygon' else [coords]
                                elif geom_type == 'Point':
                                    esri_geometry['x'] = coords[0]
                                    esri_geometry['y'] = coords[1]
                                    
                                esri_feat = {
                                    "attributes": formatted_props,
                                    "geometry": esri_geometry
                                }
                                all_esri_features.append(esri_feat)
                        except Exception as e:
                            print(f"Error parsing GeoJSON feature in {filename}: {e}")

    # Download and process Shapefile zipped files
    for url, project_name in shapefile_map.items():
        print(f"Downloading Shapefile: {url} for Project: {project_name}")
        response = requests.get(url)
        if response.status_code != 200:
            print(f"Failed to download {url}")
            continue
            
        # Shapefiles consist of multiple companion files (.shp, .shx, .dbf) inside the zip
        with zipfile.ZipFile(io.BytesIO(response.content)) as z:
            # We must isolate file components to load into the shapefile Reader object
            shp_file = next((io.BytesIO(z.read(f)) for f in z.namelist() if f.endswith('.shp')), None)
            shx_file = next((io.BytesIO(z.read(f)) for f in z.namelist() if f.endswith('.shx')), None)
            dbf_file = next((io.BytesIO(z.read(f)) for f in z.namelist() if f.endswith('.dbf')), None)
            
            if not shp_file or not dbf_file:
                print(f"Incomplete shapefile contents inside zip for {url}")
                continue
                
            try:
                # Open files simultaneously using pyshp
                with shapefile.Reader(shp=shp_file, shx=shx_file, dbf=dbf_file) as sf:
                    # Capture column headers from DBF schema
                    fields = [f[0].lower() for f in sf.fields[1:]] 
                    
                    for shape_record in sf.shapeRecords():
                        shape = shape_record.shape
                        # Reconstruct database row into key/value dictionary mappings
                        record_dict = dict(zip(fields, shape_record.record))
                        
                        # Match the standard attributes schema
                        formatted_props = {
                            "Protection_ID": str(record_dict.get('name') or record_dict.get('id', '')),
                            "Information": str(record_dict.get('desc') or record_dict.get('type', '')),
                            "Project": project_name
                        }
                        
                        # Convert Shapefile coordinates structure into Esri JSON specs
                        esri_geometry = {"spatialReference": {"wkid": 4326}}
                        
                        # Shape types: 3 = PolyLine, 5 = Polygon, 1 = Point
                        if shape.shapeType in [3, 13, 23]: # PolyLine variants
                            esri_geometry['paths'] = shape.parts_as_geometry()
                        elif shape.shapeType in [5, 15, 25]: # Polygon variants
                            esri_geometry['rings'] = shape.parts_as_geometry()
                        elif shape.shapeType in [1, 11, 21]: # Point variants
                            esri_geometry['x'] = shape.points[0][0]
                            esri_geometry['y'] = shape.points[0][1]
                            
                        esri_feat = {
                            "attributes": formatted_props,
                            "geometry": esri_geometry
                        }
                        all_esri_features.append(esri_feat)
            except Exception as e:
                print(f"Error decoding Shapefile structure: {e}")

    # ====================================================
    # AGOL UPLOAD LOGIC
    # ====================================================
    if not all_esri_features:
        print("No cable features discovered.")
        return

    target_item = gis.content.get(item_id)
    flayer = target_item.layers[0]

    # Initialize column attributes tailored for Cable Protection schema
    target_fields = [
        {"name": "Protection_ID", "type": "esriFieldTypeString", "alias": "Protection ID", "nullable": True},
        {"name": "Information", "type": "esriFieldTypeString", "alias": "Information", "nullable": True},
        {"name": "Project", "type": "esriFieldTypeString", "alias": "Project", "nullable": True} 
    ]

    if not flayer.properties.fields:
        print("Initializing layer schema constraints...")
        flayer.manager.add_to_definition({"fields": target_fields})

    allowed_keys = [f['name'] for f in target_fields]
    cleaned_features = []
    for feat in all_esri_features:
        filtered_attributes = {k: v for k, v in feat['attributes'].items() if k in allowed_keys}
        feat['attributes'] = filtered_attributes
        cleaned_features.append(feat)

    try:
        current_count = flayer.query(where="1=1", return_count_only=True)
        if current_count > 0:
            print(f"Found {current_count} existing features. Clearing layer...")
            flayer.delete_features(where="1=1")
        else:
            print("Layer is already empty. Skipping wipe.")
    except Exception:
        print("Layer schema not yet initialized. Skipping wipe.")

    print(f"Pushing {len(cleaned_features)} cable features to: {target_item.title}...")
    for i in range(0, len(cleaned_features), 1000):
        chunk = cleaned_features[i:i + 1000]
        result = flayer.edit_features(adds=chunk)
        if 'addResults' in result:
            fails = [r for r in result['addResults'] if not r['success']]
            if fails:
                print(f"Batch {(i//1000)+1} had {len(fails)} processing faults. Error: {fails[0].get('error')}")

    print("Sync complete.")
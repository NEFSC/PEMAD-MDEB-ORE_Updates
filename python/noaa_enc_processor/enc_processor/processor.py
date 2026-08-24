#####################################################
## FUNCTION TO PROCESS ENCS FILES INTO SEDFS AND   ##
##  UPDATE EXISTING AGOL HOSTED FEATURE SERVICES   ##
#####################################################

import pandas as pd
import geopandas as gpd
import zipfile
import tempfile
import os
import fiona
import json
from arcgis.features import FeatureSet
from arcgis.features import FeatureLayerCollection
from .enc_preprocessor import read_enc_layer
from .code_mapper import map_column_codes

def process_and_update_features(gis, data_dir, feature_config):
    """
    Processes ENC data from ZIP files, extracts specified features, and creates SEDF 
    (spatially enabled dataframe). Then, utilizes SEDF to update corresponding hosted 
    feature layers in AGOL.
    """
    feature_results = {key: [] for key in feature_config}

    # Loop through ZIP files and extract data
    print("Starting data extraction from ENC files...")
    for zip_file in os.listdir(data_dir):
        if not zip_file.endswith(".zip"):
            continue

        print(f"Processing source file: {zip_file}")
        # Create temp folder and extract data from zip to temp folder
        zip_path = os.path.join(data_dir, zip_file)
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(temp_dir)
            except Exception as e:
                print(f"Failed to unzip {zip_file}: {e}")
                continue
            # Walk through all folders in temp folder to find .000 file    
            enc_files = [os.path.join(root, file) for root, _, files in os.walk(temp_dir) for file in files if file.endswith(".000")]
            if not enc_files:
                print(f"No .000 ENC file found in {zip_file}")
                continue
            # Read first file in folder that has .000 file extentions
            # There should only be one file with this extention
            enc_path = enc_files[0]
            try:
                layers = fiona.listlayers(enc_path)
            except Exception as e:
                print(f"Could not read layers in {zip_file}: {e}")
                continue
            # Get layer from extraction_features, set in config.py  
            for name, info in feature_config.items():
                layer_name = info["layer_name"]
                if layer_name not in layers:
                    continue

                try:
                    print(f"Calling read_enc_layer function for layer: {layer_name}")
                    # Call the function to convert any list columns to comma-separated strings
                    gdf = read_enc_layer(enc_path, layer_name)
                    
                    if gdf.empty:
                        continue
                    # Filter using the columns and values from extraction_features, set in config.py
                    filter_col = info.get("filter_col")
                    filter_val = info.get("filter_val")
                    if filter_col and filter_val and filter_col in gdf.columns:
                        gdf = gdf[gdf[filter_col] == filter_val]

                    if not gdf.empty:
                        # Add a column to the gdf stating the source file name
                        gdf["source_file"] = os.path.basename(zip_file)
                        feature_results[name].append(gdf)
                        print(f"Found {len(gdf)} features for '{name}' in layer '{layer_name}'")

                except Exception as e:
                    print(f"Error processing layer '{layer_name}' from {zip_file}: {e}")

    # Consolidate data and update AGOL directly
    print("Finished extraction. Starting ArcGIS Online updates...")
    for name, gdf_list in feature_results.items():
        if not gdf_list:
            print(f"[{name}] No data was extracted. Skipping AGOL update.")
            continue

        try:
            # Combine all alike features into one gdf
            full_gdf = gpd.GeoDataFrame(pd.concat(gdf_list, ignore_index=True), crs=gdf_list[0].crs)
            print(f"[{name}] Successfully combined {len(full_gdf)} total features.")
            print(gdf.head())
        except Exception as e:
            print(f"[{name}] failed to combine GeoDataFrames: {e}")
            continue

        # Remove wind turbines on land
        if name == "Wind_Turbines":
                source_col = 'source_file' if 'source_file' in full_gdf.columns else (
                    'SOURCE_FILE' if 'SOURCE_FILE' in full_gdf.columns else None
                )
                if source_col:
                    initial_count = len(full_gdf)
                    full_gdf = full_gdf[full_gdf[source_col] != 'US4RI1EB.zip'] # This chart has two wind turbines on land
                    removed_count = initial_count - len(full_gdf)
                    print(f"[{name}] Removed {removed_count} rows where {source_col} == 'US4RI1EB.zip'.")
        
        # Remove duplicate features in the wind_turbines layer using the FIDN column
        # Check if the current feature set is the one containing Wind Turbines
        if name == "Wind_Turbines" and 'FIDN' in full_gdf.columns:
            print(f"[{name}] Detected Wind Turbines. Applying FIDN-based deduplication...")
            
            # Identify the indexes of the rows to keep
            non_duplicate_index = full_gdf.drop_duplicates(subset=['FIDN'], keep='first').index
            
            # Filter to get only the duplicate rows for inspection
            duplicate_rows_gdf = full_gdf.loc[~full_gdf.index.isin(non_duplicate_index)]
            
            # Update duplicates_removed count
            duplicates_removed = len(duplicate_rows_gdf)
            
            if duplicates_removed > 0:
                print(f"[{name}] Found {duplicates_removed} duplicate features.")
                print(f"[{name}] Inspecting 'source_file' column for duplicates:")
                print(duplicate_rows_gdf[['FIDN', 'source_file']])
            
            # Remove duplicates: Apply the filtering to keep only one record per FIDN
            full_gdf = full_gdf.drop_duplicates(subset=['FIDN'], keep='first')
            
            # Update deduplicated_count
            deduplicated_count = len(full_gdf)
            
            # Summary Log for the deduplicated layer
            print(f"[{name}] Deduplication complete. {duplicates_removed} features removed. {deduplicated_count} features retained.")
            
        elif name == "Wind_Turbines" and 'FIDN' not in full_gdf.columns:
            print(f"[{name}] Warning: Wind_Turbines layer found, but 'FIDN' column is missing. Skipping deduplication.")
            
        else:
            # For all other layers, there are no duplicates. 
            print(f"[{name}] Not the target layer. Skipping deduplication.")
          
        mapping_csv_path = feature_config[name].get("mapping_csv")

        # Call mapping function to convert any coded data into a non-coded, readable value    
        if mapping_csv_path:
            # If a mapping file is defined in the config, call the function
            # and overwrite full_gdf with the processed result.
            full_gdf = map_column_codes(full_gdf, mapping_csv_path)
        else:
            print(f"[{name}] No mapping CSV configured. Proceeding with original data.")

        # Map the Function column to the Construction Status column for Wind Turbines
        # Light support = Under construction/operational, NA = proposed
        if name == "Wind_Turbines":
            print(f"[{name}] Filling blank OBJNAMs and splitting project info...")

            # Define the manual mapping for blank OBJNAM rows based on FIDN
            # Format: {FIDN_Value: "Project Name WTG ID"}
            fidn_fix_map = {
                69282477: "Sunrise Wind WTG AR16",
                36834519: "Block Island Wind Farm WTG WTG-5",
                36834553: "Block Island Wind Farm WTG WTG-3",
                36834504: "Block Island Wind Farm WTG WTG-4",
                36834554: "Block Island Wind Farm WTG WTG-1",
                36834514: "Block Island Wind Farm WTG WTG-2"
            }

            # Fill blanks only where OBJNAM is null or empty
            def fill_missing_objnam(row):
                # Check if OBJNAM is null or just whitespace
                if pd.isna(row['OBJNAM']) or str(row['OBJNAM']).strip() == "":
                    # Return the mapped value if FIDN exists in the dictionary
                    return fidn_fix_map.get(row['FIDN'], row['OBJNAM'])
                return row['OBJNAM']

            if 'FIDN' in full_gdf.columns:
                full_gdf['OBJNAM'] = full_gdf.apply(fill_missing_objnam, axis=1)

            # Run splitting logic to split OBJNAM column into project name and wind turbine ID
            if 'OBJNAM' in full_gdf.columns:
                # Split the string at ' WTG ' (including spaces to keep it clean)
                # n=1 ensures we only split at the first occurrence
                split_cols = full_gdf['OBJNAM'].str.split(' WTG ', n=1, expand=True)
                
                # Assign to new columns
                full_gdf['PROJECT'] = split_cols[0]
                # We add 'WTG ' back to the second part so it reads 'WTG AE10'
                full_gdf['WIND_TURBINE_ID'] = split_cols[1]
            
            def determine_status(val):
                # Handle Nulls/Blanks immediately
                if pd.isna(val) or str(val).strip() == "":
                    return "Proposed"
                # Clean and lowercase for comparison
                val_clean = str(val).strip().lower()
                # Compare against lowercase "light support"
                if val_clean == "light support":
                    return "Under Construction/Operational"
                 # Catch-all for other non-blank values
                return "Proposed" 
            full_gdf['CONSTRUCTION_STATUS'] = full_gdf['FUNCTN'].apply(determine_status)

        # Map the Function column to the Construction Status column for Wind Turbines
        # Light support = Under construction/operational, NA = proposed
        if name == "Offshore_Substations":
            print(f"[{name}] Filtering out observation platforms")
            if 'CATOFP' in full_gdf.columns:
                # Keep only rows that are NOT 'observation/research platform'
                full_gdf = full_gdf[full_gdf['CATOFP'] != 'observation/research platform']
            
            print(f"[{name}] Filling blank OBJNAMs and splitting project info...")
            # Define the manual mapping for blank OBJNAM rows based on FIDN
            # Format: {FIDN_Value: "Project Name OSS ID"}
            fidn_fix_map = {
                102474376: "Coastal Virginia Offshore Substation OSS T3G15"
            }

            # Fill blanks only where OBJNAM is null or empty
            def fill_missing_objnam(row):
                # Check if OBJNAM is null or just whitespace
                if pd.isna(row['OBJNAM']) or str(row['OBJNAM']).strip() == "":
                    # Return the mapped value if FIDN exists in the dictionary
                    return fidn_fix_map.get(row['FIDN'], row['OBJNAM'])
                return row['OBJNAM']

            if 'FIDN' in full_gdf.columns:
                full_gdf['OBJNAM'] = full_gdf.apply(fill_missing_objnam, axis=1)

            # Run splitting logic to split OBJNAM column into project name and wind turbine ID
            if 'OBJNAM' in full_gdf.columns:
                # Split the string at ' PROD ' or ' Offshore Substation OSS ' (including spaces to keep it clean)
                pattern = r' PROD | Offshore Substation OSS '
                split_cols = full_gdf['OBJNAM'].str.split(pattern, n=1, expand=True, regex=True)
                
                # Assign to new columns
                full_gdf['PROJECT'] = split_cols[0]
                # We add 'WTG ' back to the second part so it reads 'WTG AE10'
                full_gdf['OSS_ID'] = split_cols[1]

        # Define AGOL item ID
        agol_id = feature_config[name].get("agol_item_id")
        if not agol_id:
            print(f"[{name}] No AGOL item ID configured. Skipping upload.")
            continue
            
        try:
            print(f"[{name}] Connecting to AGOL item {agol_id}...")
            item = gis.content.get(agol_id)
            flc = FeatureLayerCollection.fromitem(item)
            agol_layer_index = feature_config[name].get("agol_layer_index", 0)
            target_layer = flc.layers[agol_layer_index]
            
            # Identify Target WKID
            props = target_layer.properties
            target_crs_wkid = props.get('spatialReference', {}).get('wkid') or \
                              props.get('extent', {}).get('spatialReference', {}).get('wkid') or 3857
            
            print(f"[{name}] Target WKID detected: {target_crs_wkid}")

            # Reproject and clean GeoDataFrame
            full_gdf = full_gdf.to_crs(epsg=target_crs_wkid)
            full_gdf = full_gdf[full_gdf.geometry.notnull()] # Remove any empty geometries

            # Convert to FeatureSet via GeoJSON
            # This is more stable than SEDF in GitHub Actions/Linux
            print(f"[{name}] Converting to FeatureSet...")
            geojson_payload = json.loads(full_gdf.to_json())
            fset = FeatureSet.from_geojson(geojson_payload)

            # Manual Spatial Reference Injection
            target_sr = {'wkid': int(target_crs_wkid)}
            for feat in fset.features:
                if feat.geometry:
                    feat.geometry['spatialReference'] = target_sr
            
            # Truncate and Upload
            print(f"[{name}] Truncating all existing features in AGOL layer...")
            target_layer.manager.truncate()
            
            print(f"[{name}] Appending {len(fset.features)} new features to AGOL layer...")
            result = target_layer.edit_features(adds=fset.features)
            
            # Check results
            add_results = result.get('addResults', [])
            success_count = sum(1 for r in add_results if r.get('success'))
            
            if success_count == len(fset.features):
                print(f"[{name}] AGOL update successful. {success_count} features added.")
            else:
                errors = [r.get('error') for r in add_results if not r.get('success')]
                print(f"[{name}] Warning: Only {success_count}/{len(fset.features)} succeeded.")
                if errors:
                    print(f"First error: {errors[0]}")

        except Exception as e:
            print(f"[{name}] An unexpected error occurred: {e}")
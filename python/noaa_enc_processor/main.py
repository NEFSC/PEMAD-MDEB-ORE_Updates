#############################################
##      MAIN SCRIPT TO RUN WORKFLOW        ##
#############################################

import os
from arcgis.gis import GIS
from enc_processor import config, downloader, processor, field_updater
from boulder_relocation_processor import boulder_config, boulder_relocation_updater
from cable_protection_processor import cable_protection_config, cable_protection_updater

def run_workflow():
    """
    Executes the full workflow: download ENCs, process files, update AGOL features services,
    and update feature service field defintions.

    """
    # 1. Define .env variables to log into AGOL
    # Get credentials securely using os.getenv()
    portal_url = os.getenv("ARCGIS_URL")
    username = os.getenv("ARCGIS_USERNAME")
    password = os.getenv("ARCGIS_PASSWORD")

    # 2. Connect to ArcGIS Online
    try:
        print("---  Connecting to ArcGIS Online...  ---")
        gis = GIS(url=portal_url, username=username, password=password)
        print("---  Successfully connected  ---")
    except Exception as e:
        print(f"Could not connect to ArcGIS Online. Error: {e}")
        return

    # 3. Download the chart data using the downloader
    downloader.download_charts_to_disk(
        config.charts_to_download, 
        config.target_folder_path
    )

    # 4. Process the downloaded files and update AGOL
    processor.process_and_update_features(
        gis=gis,
        data_dir=config.target_folder_path,
        feature_config=config.extraction_features
    )

    # 5. Update the AGOL field names (aliases) and descriptions for increased user interoperability
    field_updater.update_field_definitions(
        gis=gis,
        mapper = config.item_id_csv_map
    )

    # 6. Update the AGOL boulder relocation feature service
    boulder_relocation_updater.update_boulder_layer(
        gis=gis,
        item_id = boulder_config.boulder_agol_id,
        geojson_map=boulder_config.geojson_boulder_projects, 
        csv_path=boulder_config.csv_file_path,
        extra_points=boulder_config.added_points
    )

    # 7. Update the AGOL cable protection feature service
    cable_protection_updater.update_cable_protection_layer(
        gis=gis,
        item_id=cable_protection_config.cable_agol_id,
        geojson_map=cable_protection_config.geojson_cable_protection_projects,
        shapefile_map=cable_protection_config.shapefile_cable_protection_projects
    )

# Run the workflow
if __name__ == "__main__":
    run_workflow()
    print("Workflow complete.")
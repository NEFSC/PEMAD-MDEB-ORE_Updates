#############################################
##        CONFIGURATION VARIABLES          ##
#############################################

from pathlib import Path
import os

# Create a list of ENCs to download
charts_to_download = ["US4NY1BY.zip", "US4RI1CB.zip", "US4MA1CC.zip", "US4MA1CD.zip", 
"US4MA1CE.zip", "US4MA1DE.zip", "US4MA1DD.zip", "US4MA1DC.zip", "US4RI1DB.zip", 
"US4NY1CY.zip", "US4NJ1FH.zip", "US4NJ1FG.zip", "US4NY1BM.zip", "US5RI1BE.zip", 
"US4NY1BX.zip", "US4VA1AG.zip", "US4VA1AH.zip", "US4VA1AI.zip", "US4VA1BG.zip", 
"US4VA1BH.zip", "US4VA1BI.zip", "US4RI1EA.zip", "US4MA1EE.zip", "US4NY1BW.zip", "US4VA1AF.zip"]

# Set a folder location on disc to download the chart data to 
base_dir = Path(__file__).resolve().parent.parent.parent.parent
target_folder_path = base_dir / "data-raw" / "ENC"

# Get AGOL item ID credentials securely using os.getenv()
turbine_agol_id = os.getenv("TURBINE_ITEM_ID")
#buoy_agol_id = os.getenv("BUOY_ITEM_ID")
cable_agol_id = os.getenv("CABLE_ITEM_ID")
substation_agol_id = os.getenv("SUBSTATION_ITEM_ID")

# Define the file path for the S-57 data dictionary CSV
data_dict_csv_path = base_dir / "data" / "csv" / "S57_ENC_Data_Dictionary.csv"

# Define the features to extract from ENC
extraction_features = {
    "Wind_Turbines": {
        "layer_name": "LNDMRK", # Name of ENC landmark layer
        "filter_col": "CATLMK",
        "filter_val": "19",  # Turbines are 19 catlmk
        "output_name": "NOAA_ENC_WTG",
        "agol_item_id": turbine_agol_id,
        "agol_layer_index": 0,
        "mapping_csv": data_dict_csv_path},

    "Submarine_Cables":{
        "layer_name": "CBLSUB", # Name of ENC submarine cable layer  
        "filter_col": "CATCBL",
        "filter_val": 1, # Power cables are 1 catcbl
        "output_name": "NOAA_ENC_PowerCables",
         "agol_item_id": cable_agol_id,
         "agol_layer_index": 0,
         "mapping_csv": data_dict_csv_path},
    
    "Offshore_Substations":{
        "layer_name": "OFSPLF", # Name of ENC offshore substation layer  
        "filter_col": None, # No filter for substations
        "filter_val": None,
        "output_name": "NOAA_ENC_OSS",
        "agol_item_id": substation_agol_id,
        "agol_layer_index": 0,
        "mapping_csv": data_dict_csv_path},

    # "Buoys":{
    #     "layer_name": "BOYSPP", # Name of ENC buoy layer 
    #     "filter_col": None, # Could filter using "CATSPM", need to determine correct filter values
    #     "filter_val": None,
    #     "output_name": "NOAA_ENC_Buoys",
    #     "agol_item_id": buoy_agol_id,
    #     "agol_layer_index": 0,
    #     "mapping_csv": data_dict_csv_path},
}

# Define file path for the S-57 field description CSVs
turbine_csv_path = base_dir / "data" / "csv" / "S57_ENC_Object_Definitions_LNDMRK.csv"
#buoy_csv_path = base_dir / "data" / "csv" / "S57_ENC_Object_Definitions_BOYSPP.csv"
cable_csv_path = base_dir / "data" / "csv" / "S57_ENC_Object_Definitions_CBLSUB.csv"
substation_csv_path = base_dir / "data" / "csv" / "S57_ENC_Object_Definitions_OFSPLF.csv"

# Map the AGOL feature service item IDs to their corresponding CSV field definition file paths
item_id_csv_map = {
    turbine_agol_id: turbine_csv_path,
    #buoy_agol_id: buoy_csv_path,
    cable_agol_id: cable_csv_path,
    substation_agol_id: substation_csv_path
}
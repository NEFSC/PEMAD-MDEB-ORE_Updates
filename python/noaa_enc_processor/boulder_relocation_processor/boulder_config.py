#############################################
##        CONFIGURATION VARIABLES          ##
#############################################

from pathlib import Path
import os

# Path to csv file for Empire Wind boulder relocation
config_file = Path(__file__).resolve()
project_root = config_file.parents[3]
csv_file_path = project_root / "data" / "csv" / "EmpireWind_BoulderRelocation.csv"

# Map the URL to the specific Project Name
geojson_boulder_projects = {
    "https://www.quintham.com//EMIN/8/23/246/GeoJson.zip": "South Fork Wind",
    "https://www.quintham.com//EMIN/8/28/130/GeoJson.zip": "Sunrise Wind",
    "https://www.quintham.com//EMIN/8/29/88/GeoJson.zip": "Revolution Wind",
    "https://www.quintham.com//EMIN/5/16/34/GeoJson.zip": "Vineyard Wind 1"
}

# Hard-coded dictionary of points
# These points exist in the RWSC dataset but nowhere on Quintham, hardcoding them here
added_points = [
    {
        "Boulder_ID": "Boulder 44",  
        "Lat": 41.191333,              
        "Lon": -71.143883,             
        "Information": "",
        "Project": "Revolution Wind"
    },
    {
        "Boulder_ID": "Boulder 156",  
        "Lat": 41.20355,                
        "Lon": -71.153617,               
        "Information": "",
        "Project": "Revolution Wind"
    },
    {
        "Boulder_ID": "MC_07864",  
        "Lat": 40.9935,                
        "Lon": -71.127833,               
        "Information": "",
        "Project": "Sunrise Wind"
    },
    {
        "Boulder_ID": "FUG_OFFS_1427",  
        "Lat": 40.863733,                
        "Lon": -71.434317,               
        "Information": "",
        "Project": "Sunrise Wind"
    },
    {
        "Boulder_ID": "FUG_ONSH_4465",  
        "Lat": 40.7249,                
        "Lon": -72.826767,               
        "Information": "",
        "Project": "Sunrise Wind"
    }
]

boulder_agol_id = os.getenv("BOULDER_ITEM_ID")
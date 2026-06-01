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
gpx_boulder_projects = {
    "https://www.quintham.com//EMIN/8/28/130/GPX.zip": "Sunrise Wind"
}

boulder_agol_id = os.getenv("BOULDER_ITEM_ID")
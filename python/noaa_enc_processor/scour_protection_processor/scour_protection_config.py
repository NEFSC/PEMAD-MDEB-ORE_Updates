#############################################
##        CONFIGURATION VARIABLES          ##
#############################################

from pathlib import Path
import os

# Map the URL to the specific Project Name
geojson_scour_protection_projects = {
    "https://www.quintham.com//EMIN/8/28/252/GeoJson.zip": "Sunrise Wind",
    "https://www.quintham.com//EMIN/5/16/253/GeoJson.zip": "Vineyard Wind 1"
}

scour_agol_id = os.getenv("SCOUR_ITEM_ID")
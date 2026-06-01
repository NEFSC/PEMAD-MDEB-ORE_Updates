#############################################
##        CONFIGURATION VARIABLES          ##
#############################################

from pathlib import Path
import os

# Map the URL to the specific Project Name
geojson_cable_protection_projects = {
    "https://www.quintham.com//EMIN/8/23/51/GeoJson.zip": "South Fork Wind",
    "https://www.quintham.com//EMIN/8/28/265/GeoJson.zip": "Sunrise Wind",
    "https://www.quintham.com//EMIN/5/16/48/GeoJson.zip": "Vineyard Wind 1"
}

shapefile_cable_protection_projects = {
    "https://www.quintham.com//EMIN/8/29/115/Shapefile.zip": "Revolution Wind"
}

cable_agol_id = os.getenv("CABLE_ITEM_ID")
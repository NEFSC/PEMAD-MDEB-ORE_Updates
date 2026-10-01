#############################################
##        CONFIGURATION VARIABLES          ##
#############################################

from pathlib import Path
import os

# Empire Wind public feature service contains cable protection data

# Feature service for Empire Wind boulder data
empire_feature_service_url = "https://services-eu1.arcgis.com/svnWw1yovvhlm3ej/arcgis/rest/services/Boulder_Locations__2024_08_15/FeatureServer"

# Define layer indices to pull data from (Layers containing cable mattressing points)
layer_indices = [0, 1, 2, 5, 6, 8, 9, 11, 12, 19, 20, 21]

# Mapping field names to my AGOL schema
field_mapping = {
    "Protection_ID": "Mattress",    
    "Information": "Descriptio",  
    "Project": "Empire Wind"           # set to Empire Wind
}

# Map the URL to the specific Project Name
geojson_cable_protection_projects = {
    "https://www.quintham.com//EMIN/8/23/51/GeoJson.zip": "South Fork Wind",
    "https://www.quintham.com//EMIN/8/28/265/GeoJson.zip": "Sunrise Wind",
    "https://www.quintham.com//EMIN/5/16/48/GeoJson.zip": "Vineyard Wind 1"
}

gpx_cable_protection_projects = {
    "https://www.quintham.com//EMIN/8/29/115/GPX.zip": "Revolution Wind"
}

cable_protection_agol_id = os.getenv("CABLE_PROTECTION_ITEM_ID")
# Utilitaire de récupération du desc (L2J) à partir du type (A320)

import requests

def fetch_icao_type_descriptions(url="https://raw.githubusercontent.com/wiedehopf/tar1090-db/master/icao_aircraft_types.json"):
    response = requests.get(url)
    response.raise_for_status()
    return response.json()

def get_type_description(icao_type, type_dict):
    if icao_type:
        info = type_dict.get(icao_type.upper())
        if info:
            return info.get("desc")
    return None
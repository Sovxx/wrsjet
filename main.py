import configparser
import requests
import csv
import time
from datetime import datetime
import logging

from utils_geo import get_distance, get_azimuth
from utils_icao import fetch_icao_type_descriptions, get_type_description

import map

config = configparser.ConfigParser()
config.read("config.ini")

LAT = float(config["location"]["lat"])
if not (-90 <= LAT <= 90):
    raise ValueError("Latitude must be between -90 and 90°")
LON = float(config["location"]["lon"])
if not (-180 <= LON <= 180):
    raise ValueError("Longitude must be between -180 and 180°")
RADIUS = float(config["location"]["radius"])
if not (0 < RADIUS <= 250):
    raise ValueError("Longitude must be between 0 and 250 NM")

MIN_ALT = int(config["altitude"]["min_alt"])
MAX_ALT = int(config["altitude"]["max_alt"])

def parse_set(s):
    return set(item.strip() for item in s.split(",") if item.strip())

CALLSIGN_BLACKLIST = parse_set(config["filters"]["callsign_blacklist"])
REGIS_BLACKLIST = parse_set(config["filters"]["regis_blacklist"])
DESC_BLACKLIST = parse_set(config["filters"]["desc_blacklist"])

CSV_FILE = "records.csv"

API_URL = f"https://api.adsb.lol/v2/lat/{LAT}/lon/{LON}/dist/{RADIUS}"
"""
documentation :
https://api.adsb.lol/docs#/v2/v2_point_v2_lat__lat__lon__lon__dist__radius__get
example :
curl -X 'GET' 'https://api.adsb.lol/v2/lat/48.6058/lon/2.6717/dist/5' -H 'accept: application/json'
"""

logging.basicConfig(
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("error.log"),  # File handler
        logging.StreamHandler()            # Stream handler for console output
    ]
)

def save_csv(row):
    with open(CSV_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(row)

def check_aircraft() -> bool:
    """
    Add a record in the csv file if aircraft(s) found

    Returns:
        bool: True if aircraft(s) found
    """
    now = datetime.now()
    timestamp = now.replace(microsecond=0).isoformat()

    excitation = False
    try:
        response = requests.get(API_URL, timeout=10)
        response.raise_for_status()
        data = response.json()

        for ac in data.get("ac", []):
            callsign = ac.get("flight")  # ex: JAL924
            regis = ac.get("r")  # ex: F-GSEX
            hex = ac.get("hex")
            type = ac.get("t")  # ex: A320
            desc = get_type_description(type, type_data)  # ex: L2J
            alt = ac.get("alt_baro")  # ft
            vspeed = ac.get("baro_rate")  # ft/min
            lat = ac.get("lat")
            lon = ac.get("lon")
            track = (
                None if (ac.get("track") is None) else int(round(ac.get("track")))
            )  # aircraft own track in degrees
            dist = get_distance(LAT, LON, lat, lon)
            azimuth = get_azimuth(LAT, LON, lat, lon)  # from surveillance point

            if alt:
                if not (MIN_ALT <= alt <= MAX_ALT):
                    continue  # skip this aircraft

            if callsign:
                if any(callsign.startswith(prefix) for prefix in CALLSIGN_BLACKLIST):
                    continue
            if regis in REGIS_BLACKLIST:
                continue
            if desc in DESC_BLACKLIST:
                continue

            row = [
                timestamp,
                callsign,
                regis,
                hex,
                type,
                desc,
                alt,
                vspeed,
                lat,
                lon,
                track,
                dist,
                azimuth,
            ]
            save_csv(row)

            print("🛬 Aircraft detected :", row)
            map.main(verbose=False)
            if type != "L1P":
                excitation = True
        return excitation

    except Exception as e:
        logging.error("API error: %s", e)
        return False

if __name__ == "__main__":

    type_data = fetch_icao_type_descriptions()
    if get_type_description("A320", type_data) != "L2J":
        raise ValueError("ICAO type descriptions database is unusable")

    header = [
            "timestamp",
            "callsign",
            "regis",
            "hex",
            "type",
            "desc",
            "alt",
            "vspeed",
            "lat",
            "lon",
            "track",
            "dist",
            "azimuth",
        ]

    # Create csv header line if csv file does not exist
    try:
        with open(CSV_FILE, "x", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(header)
    except FileExistsError:
        pass

    map.main(verbose=False)

    print(f"{sorted(CALLSIGN_BLACKLIST)=}")
    print(f"{sorted(REGIS_BLACKLIST)=}")
    print(f"{sorted(DESC_BLACKLIST)=}")
    print(
        f"📡 Monitoring airspace within {RADIUS} NM from https://www.openstreetmap.org/#map=9/{LAT}/{LON} between {MIN_ALT} and {MAX_ALT} ft"
    )
    print(f"Format: {header}")

    while True:
        delay = 10 if check_aircraft() else 40
        time.sleep(delay)

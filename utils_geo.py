from geographiclib.geodesic import Geodesic


def get_distance(lat1, lon1, lat2, lon2) -> float:
    """
    Returns:
        float: Distance in NM betweeen point 1 and point 2
    """
    if None in (lat1, lon1, lat2, lon2):
        return None
    if not all(isinstance(angle, float) for angle in [lat1, lon1, lat2, lon2]):
        raise TypeError(f"Arguments for get_distance must be float or None, not \
                        {type(lat1).__name__} {type(lon1).__name__} \
                        {type(lat2).__name__} {type(lon2).__name__}.")
    if not all(-90 <= lat <= 90 for lat in [lat1, lat2]):
        raise ValueError("Latitude must be between -90 and 90°")
    if not all(-180 <= lon <= 180 for lon in [lon1, lon2]):
        raise ValueError("Longitude must be between -180 and 180°")
    g = Geodesic.WGS84.Inverse(lat1, lon1, lat2, lon2)
    distance_m = g["s12"]  # distance in meters
    distance_nm = distance_m / 1852  # conversion to nautical miles
    return round(distance_nm, 2)


def get_azimuth(lat1, lon1, lat2, lon2) -> int:
    """
    Returns:
        int: Azimuth of point 2 seen from point 1
    """
    if None in (lat1, lon1, lat2, lon2):
        return None
    if not all(isinstance(angle, float) for angle in [lat1, lon1, lat2, lon2]):
        raise TypeError(f"Arguments for get_azimuth must be float or None, not \
                        {type(lat1).__name__} {type(lon1).__name__} \
                        {type(lat2).__name__} {type(lon2).__name__}.")
    if not all(-90 <= lat <= 90 for lat in [lat1, lat2]):
        raise ValueError("Latitude must be between -90 and 90°")
    if not all(-180 <= lon <= 180 for lon in [lon1, lon2]):
        raise ValueError("Longitude must be between -180 and 180°")

    g = Geodesic.WGS84.Inverse(lat1, lon1, lat2, lon2)
    azimuth = g["azi1"]  # +/- from North (ex : -45 = NW)
    if azimuth < 0:
        azimuth += 360  # aeronautical (ex: 315 = NW)
    return int(round(azimuth))

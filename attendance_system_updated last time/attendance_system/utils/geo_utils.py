from math import radians, sin, cos, sqrt, atan2


def distance_meters(lat1, lon1, lat2, lon2):
    """Great-circle distance between two points, in meters."""
    R = 6371000  # Earth radius in meters
    phi1, phi2 = radians(lat1), radians(lat2)
    d_phi = radians(lat2 - lat1)
    d_lambda = radians(lon2 - lon1)

    a = sin(d_phi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(d_lambda / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c


def within_geofence(lat, lon, center_lat, center_lon, radius_m):
    return distance_meters(lat, lon, center_lat, center_lon) <= radius_m

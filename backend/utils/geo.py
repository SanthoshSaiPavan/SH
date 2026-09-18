"""Haversine distance and geofence utilities."""
import math

EARTH_RADIUS_KM = 6371.0


def haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in km between two points."""
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2)
    return EARTH_RADIUS_KM * 2 * math.asin(math.sqrt(min(1.0, a)))


def is_within_geofence(point_lat, point_lng, center_lat, center_lng, radius_km) -> bool:
    return haversine(point_lat, point_lng, center_lat, center_lng) <= radius_km


def point_to_line_distance(point, line_start, line_end) -> float:
    """Minimum km distance from point to the segment line_start→line_end.

    Points are (lat, lng). Uses an equirectangular projection around the
    segment, which is accurate enough at the few-hundred-km scale of a leg.
    """
    lat0 = math.radians((line_start[0] + line_end[0]) / 2)

    def project(p):
        return (math.radians(p[1]) * math.cos(lat0) * EARTH_RADIUS_KM,
                math.radians(p[0]) * EARTH_RADIUS_KM)

    px, py = project(point)
    ax, ay = project(line_start)
    bx, by = project(line_end)
    dx, dy = bx - ax, by - ay
    seg_len_sq = dx * dx + dy * dy
    if seg_len_sq == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg_len_sq))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def bearing(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Initial compass bearing in degrees (0–360) from point 1 to point 2."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lng2 - lng1)
    x = math.sin(dl) * math.cos(phi2)
    y = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def interpolate(lat1: float, lng1: float, lat2: float, lng2: float, fraction: float):
    """Linear interpolation between two coordinates (fine for short steps)."""
    f = max(0.0, min(1.0, fraction))
    return lat1 + (lat2 - lat1) * f, lng1 + (lng2 - lng1) * f

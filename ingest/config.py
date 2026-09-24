"""Site configuration for the Thorndyke Bay portal."""

SITE = {
    "name": "Thorndyke Bay",
    "lat": 47.806,
    "lon": -122.735,
    "timezone": "America/Los_Angeles",
}

# NOAA CO-OPS tide prediction station. Lofall is a subordinate station
# (high/low predictions only); Bangor Wharf is its harmonic reference.
TIDE_STATION = {"id": "9445088", "name": "Lofall", "lat": 47.8150, "lon": -122.6567}
TIDE_DAYS = 35

# National Weather Service
NWS_GRID = {"office": "SEW", "x": 114, "y": 80}
NWS_MARINE_ZONE = "PZZ135"  # Hood Canal
NWS_OBS_STATIONS = 3        # nearest N observation stations to include
NWS_OBS_HOURS = 72

# api.weather.gov asks for a User-Agent that identifies the app and a contact.
USER_AGENT = "acantha-thorndyke-portal (https://github.com/RobertsLab/acantha)"

# Bounding box used for spatial queries (lon/lat, WGS84)
BBOX = {"xmin": -122.85, "ymin": 47.72, "xmax": -122.62, "ymax": 47.90}

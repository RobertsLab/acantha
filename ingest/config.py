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

# On-farm sensors (Phase 2), read from The Things Network (TTN) Storage
# Integration. Credentials come from the environment and are never committed:
#   TTN_APP_ID, TTN_API_KEY   (GitHub Actions secrets in CI)
#   SENSORS_MOCK=1            generate realistic fake data instead (no hardware needed)
TTN_CLUSTER = "nam1"          # North America: nam1.cloud.thethings.network
SENSOR_RETENTION_DAYS = 7     # history kept in the published sensors.json
SENSOR_STALE_MIN = 60         # no uplink for this long -> "stale"
SENSOR_OFFLINE_MIN = 360      # ... and this long -> "offline"

# One entry per deployed node. `id` is the TTN end-device ID. `elevation_ft`
# is the probe height in ft MLLW, used to flag readings taken while the probe
# is out of the water. `temp_field` / `battery_field` name the keys in the
# device's decoded payload (depends on the payload formatter); if omitted,
# common names are tried (temp_c, TempC1, temperature, ... / BatV, battery_v).
# Positions are placeholders until the site visit.
SENSORS = [
    {"id": "thorndyke-upper", "name": "Upper beach", "lat": 47.8072, "lon": -122.7372,
     "elevation_ft": 5.0, "placement": "In-bag, upper intertidal"},
    {"id": "thorndyke-mid", "name": "Mid beach", "lat": 47.8064, "lon": -122.7355,
     "elevation_ft": 1.5, "placement": "In-bag, mid intertidal"},
    {"id": "thorndyke-float", "name": "Subtidal float", "lat": 47.8053, "lon": -122.7336,
     "elevation_ft": -4.0, "placement": "Probe 1 m below float"},
]

# Observed rain (Stage IV at the site + nearby CoCoRaHS gauges), for the rain closure watch.
RAIN_HOURS = 7 * 24           # hourly history kept in rain.json
RAIN_GAUGE_MAX_KM = 15        # CoCoRaHS gauges within this distance
RAIN_GAUGE_MAX_N = 5          # ... nearest N that have reported
RAIN_GAUGE_DAYS = 4           # daily reports looked back over

# UW LiveOcean model (nowcast + ~2-3 day forecast), read over OPeNDAP. The public
# aggregation is surface-only temp/salt/zeta; see docs/liveocean-plan.md.
# Servers are tried in order. The NANOOS/OSU THREDDS (nanoos.ceoas.oregonstate.edu)
# was unreachable when this was written; add its dataset path here once confirmed.
LIVEOCEAN_URLS = [
    "https://eds.ioos.us/thredds/dodsC/ioos/nanoos/liveocean/NANOOS_Live_Ocean_best.ncd",
]
LIVEOCEAN_HINDCAST_DAYS = 7
# Nearest wet model cells (cas7 grid, ~500 m). lat/lon are the cell centers, checked
# each run so a model regrid fails loudly instead of reading the wrong place.
LIVEOCEAN_CELLS = [
    {"id": "thorndyke", "name": "Thorndyke Bay mouth", "eta": 788, "xi": 553,
     "lat": 47.8041, "lon": -122.7357},
    {"id": "dabob", "name": "ORCA Dabob Bay buoy", "eta": 788, "xi": 543,
     "lat": 47.8041, "lon": -122.8030},  # for model-vs-buoy comparison
]

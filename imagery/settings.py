"""Imagery settings. Site and BBOX come from ingest/config.py so both pipelines agree."""
from __future__ import annotations

import sys
from pathlib import Path

INGEST = Path(__file__).resolve().parent.parent / "ingest"
sys.path.insert(0, str(INGEST))

from config import BBOX, SITE, TIDE_STATION  # noqa: E402,F401

# STAC catalogs, tried in order. Earth Search serves public S2 COGs with no signing;
# Planetary Computer needs a (free, anonymous) SAS token, handled by planetary-computer.
CATALOGS = [
    {"name": "earth-search", "url": "https://earth-search.aws.element84.com/v1",
     "s2": "sentinel-2-l2a", "bands": {"red": "red", "green": "green", "blue": "blue", "scl": "scl"}},
    {"name": "planetary-computer", "url": "https://planetarycomputer.microsoft.com/api/stac/v1",
     "s2": "sentinel-2-l2a", "bands": {"red": "B04", "green": "B03", "blue": "B02", "scl": "SCL"}},
]

LOOKBACK_DAYS = 30        # searched each run; scenes already in imagery.json are skipped
RETAIN_DAYS = 30          # products older than this are pruned
MIN_CLEAR_PCT = 10        # render true color only if at least this much of the AOI is clear
LATEST_CLEAR_SITE_PCT = 70  # "latest clear view" needs this much clear sky around the site
SITE_RADIUS_M = 1500

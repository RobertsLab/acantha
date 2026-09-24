"""WA Department of Health shellfish layers (ArcGIS feature services, public).

- Biotoxin_Closure_Zones: recreational biotoxin closure zones. SPECIEDESCRIPTION
  is "None" when open, otherwise the species that are closed.
- Recreational_Shellfish_Beaches: per-beach status; UPDATED gives freshness.
- Commercial_Shellfish_Growing_Areas: commercial classification polygons.
"""
from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlencode

from config import BBOX, SITE
from sources.common import get_json, iso

BASE = "https://services8.arcgis.com/rGGrs6HCnw87OFOT/arcgis/rest/services"
MAP_URL = "https://doh.wa.gov/community-and-environment/shellfish/recreational-shellfish/illness-prevention/biotoxins"

CLASS_KEYS = {
    "approved": "approved", "conditional": "conditional", "conditionally approved": "conditional",
    "restricted": "restricted", "prohibited": "prohibited",
}


def _query(layer: str, point: bool = False, simplify: bool = True) -> dict:
    params = {
        "where": "1=1", "outFields": "*", "f": "geojson", "inSR": 4326, "outSR": 4326,
        "spatialRel": "esriSpatialRelIntersects",
    }
    if point:
        params.update(geometry=f"{SITE['lon']},{SITE['lat']}", geometryType="esriGeometryPoint",
                      returnGeometry="false")
    else:
        params.update(geometry=f"{BBOX['xmin']},{BBOX['ymin']},{BBOX['xmax']},{BBOX['ymax']}",
                      geometryType="esriGeometryEnvelope")
        if simplify:
            params.update(geometryPrecision=5, maxAllowableOffset=0.0001)
    data = get_json(f"{BASE}/{layer}/FeatureServer/0/query?{urlencode(params)}")
    if "error" in data:
        raise RuntimeError(data["error"].get("message", "ArcGIS error"))
    return data


def _epoch(ms):
    return iso(datetime.fromtimestamp(ms / 1000, tz=timezone.utc)) if ms else None


def _zone(props: dict) -> dict:
    closed_for = (props.get("SPECIEDESCRIPTION") or "").strip()
    closed = bool(closed_for) and closed_for.lower() != "none"
    return {
        "name": props.get("C_ZNAME"), "zone_id": props.get("ZONEID"), "closed": closed,
        "status": f"Closed: {closed_for}" if closed else "Open",
    }


def _area(props: dict) -> dict:
    cls = (props.get("CLASS") or "Unclassified").strip()
    return {
        "name": props.get("NAME"), "classification": cls,
        "class_key": CLASS_KEYS.get(cls.lower(), "unclassified"),
        "reason": props.get("Reason"), "updated": _epoch(props.get("Updated")),
    }


def fetch() -> dict:
    zones = _query("Biotoxin_Closure_Zones")
    for f in zones["features"]:
        f["properties"] = _zone(f["properties"])

    areas = _query("Commercial_Shellfish_Growing_Areas")
    for f in areas["features"]:
        f["properties"] = _area(f["properties"])

    beaches = []
    for f in _query("Recreational_Shellfish_Beaches", simplify=False)["features"]:
        p = f["properties"]
        beaches.append({
            "name": p.get("BEACHNAME"), "status": p.get("FINALSTATUS"),
            "closed_for": p.get("PopupClosedFor"), "growing_area": p.get("GROWINGAREANAME"),
            "updated": _epoch(p.get("UPDATED")),
        })
    beaches.sort(key=lambda b: b["name"] or "")

    site_zone = next((_zone(f["properties"]) for f in
                      _query("Biotoxin_Closure_Zones", point=True)["features"]), None)
    site_area = next((_area(f["properties"]) for f in
                      _query("Commercial_Shellfish_Growing_Areas", point=True)["features"]), None)

    return {
        "source": "WA Department of Health shellfish feature services",
        "source_url": MAP_URL,
        "status_updated": max((b["updated"] for b in beaches if b["updated"]), default=None),
        "site_zone": site_zone,
        "site_growing_area": site_area,
        "biotoxin": zones,
        "growing_areas": areas,
        "beaches": beaches,
        "note": "Biotoxin zones are recreational closures. Commercial harvest is governed by "
                "DOH commercial biotoxin sampling and your growing-area classification.",
    }

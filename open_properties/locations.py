"""Explicit provider location identifiers and coordinate shortcuts."""

from __future__ import annotations

from typing import Dict, List

RIGHTMOVE_LOCATIONS: Dict[str, str] = {
    "edinburgh": "REGION^475", "edinburgh-city": "REGION^475",
    "edinburgh-and-lothian": "REGION^95850", "fife": "REGION^61347",
    "falkirk": "REGION^501", "glasgow": "REGION^550",
    "manchester": "REGION^904", "london": "REGION^93917",
}
ESPC_LOCATIONS = {
    "edinburgh": "edinburgh", "east-lothian": "east-lothian",
    "midlothian": "midlothian", "west-lothian": "west-lothian", "fife": "fife",
}
ZOOPLA_LOCATIONS = {name: name for name in ["edinburgh", "glasgow", "manchester", "london"]}
DAFT_LOCATIONS = {
    "ireland": "0", "dublin": "1", "dublin-city": "33", "cork": "15",
    "cork-city": "35", "galway": "19", "galway-city": "34",
    "limerick": "17", "limerick-city": "37", "waterford": "12", "waterford-city": "38",
}
IDEALISTA_LOCATIONS = {
    "madrid": "40.4168,-3.7038", "barcelona": "41.3874,2.1686",
    "valencia": "39.4699,-0.3763", "seville": "37.3891,-5.9845",
    "lisbon": "38.7223,-9.1393", "porto": "41.1579,-8.6291",
    "rome": "41.9028,12.4964", "milan": "45.4642,9.1900", "turin": "45.0703,7.6869",
}

PROVIDER_LOCATIONS: Dict[str, Dict[str, str]] = {
    "rightmove": RIGHTMOVE_LOCATIONS, "espc": ESPC_LOCATIONS,
    "zoopla": ZOOPLA_LOCATIONS, "daft": DAFT_LOCATIONS,
    "idealista": IDEALISTA_LOCATIONS,
}


def normalise_location(value: str) -> str:
    return (value or "").strip().lower().replace(" ", "-").replace("_", "-")


def resolve(provider: str, location: str) -> str:
    provider = provider.lower()
    location = location or "edinburgh"
    if provider == "rightmove" and location.upper().startswith("REGION^"):
        return location
    if provider == "idealista" and "," in location:
        return location
    return PROVIDER_LOCATIONS.get(provider, {}).get(normalise_location(location), location)


def find(query: str = "", country: str = "") -> List[Dict[str, str]]:
    q = normalise_location(query)
    country = country.upper()
    provider_countries = {
        "rightmove": "GB", "espc": "GB", "zoopla": "GB", "daft": "IE", "idealista": "ES,IT,PT",
    }
    rows = []
    for provider, mapping in PROVIDER_LOCATIONS.items():
        if country and country not in provider_countries.get(provider, "").split(","):
            continue
        for name, value in mapping.items():
            if not q or q in name or q in value.lower():
                rows.append({"provider": provider, "portal": provider, "country": provider_countries[provider], "name": name, "value": value})
    return rows

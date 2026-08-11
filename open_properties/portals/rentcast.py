"""RentCast adapter — nationwide US sale and rental listings API."""

from __future__ import annotations

import json
import os
import subprocess
from typing import Any, Dict, List, Tuple
from urllib.parse import quote, urlencode

from ..schema import normalise_listing, utc_now_iso
from .base import PortalAdapter, SearchConfig

CITY_STATES = {
    "new york": "NY", "los angeles": "CA", "chicago": "IL", "houston": "TX",
    "phoenix": "AZ", "philadelphia": "PA", "san antonio": "TX", "san diego": "CA",
    "dallas": "TX", "austin": "TX", "san francisco": "CA", "seattle": "WA",
    "boston": "MA", "miami": "FL", "denver": "CO", "atlanta": "GA",
}
SQFT_TO_SQM = 0.09290304


class RentCastAdapter(PortalAdapter):
    name = "rentcast"
    parser_version = "rentcast-listings-v1"
    base_url = "https://api.rentcast.io/v1"

    def api_key(self) -> str:
        key = os.environ.get("RENTCAST_API_KEY", "")
        if not key:
            raise RuntimeError("RentCast requires RENTCAST_API_KEY from developers.rentcast.io")
        return key

    def location(self, config: SearchConfig) -> Tuple[str, str]:
        bits = [part.strip() for part in config.location.split(",") if part.strip()]
        city = bits[0] if bits else config.location
        state = str(config.extra.get("state") or (bits[1].upper() if len(bits) > 1 else CITY_STATES.get(city.lower(), "")))
        if not state:
            raise ValueError("RentCast needs a US state; use --state TX or --location 'Austin, TX'")
        return city, state

    def build_url(self, config: SearchConfig, offset: int = 0) -> str:
        city, state = self.location(config)
        path = "/listings/rental/long-term" if config.transaction == "rent" else "/listings/sale"
        params: Dict[str, Any] = {"city": city, "state": state, "limit": 100, "offset": offset}
        if config.min_beds or config.max_beds is not None:
            params["bedrooms"] = f"{config.min_beds or '*'}:{config.max_beds if config.max_beds is not None else '*'}"
        if config.min_baths or config.max_baths is not None:
            params["bathrooms"] = f"{config.min_baths or '*'}:{config.max_baths if config.max_baths is not None else '*'}"
        if config.min_price or config.max_price:
            params["price"] = f"{config.min_price or '*'}:{config.max_price or '*'}"
        if config.property_types:
            params["propertyType"] = config.property_types
        return f"{self.base_url}{path}?{urlencode(params)}"

    def fetch(self, key: str, url: str) -> List[Dict[str, Any]]:
        result = subprocess.run([
            "curl", "-sS", "--fail-with-body", "--max-time", "25", url,
            "-H", f"X-Api-Key: {key}", "-H", "Accept: application/json",
        ], capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "RentCast search failed")
        return json.loads(result.stdout)

    def parse_listing(self, item: Dict[str, Any], transaction: str) -> Dict[str, Any]:
        listing_id = str(item.get("id") or "")
        endpoint = "/listings/rental/long-term/" if transaction == "rent" else "/listings/sale/"
        price = item.get("price") or 0
        features = [value for value in [
            f"built {item['yearBuilt']}" if item.get("yearBuilt") else "",
            f"HOA ${item.get('hoa', {}).get('fee')}/month" if item.get("hoa", {}).get("fee") else "",
            item.get("listingType") or "", item.get("status") or "",
        ] if value]
        return normalise_listing({
            "id": listing_id, "portal": self.name,
            "url": f"{self.base_url}{endpoint}{quote(listing_id, safe='')}",
            "address": item.get("formattedAddress") or "", "title": item.get("formattedAddress") or "Property",
            "price": price, "price_text": f"${price:,.0f}" if price else "Price on application",
            "price_period": "month" if transaction == "rent" else "", "currency": "USD", "country": "US",
            "transaction": transaction, "beds": item.get("bedrooms") or 0, "baths": item.get("bathrooms") or 0,
            "property_type": item.get("propertyType") or "property", "area": item.get("city") or item.get("county") or "",
            "postcode": item.get("zipCode") or "", "latitude": item.get("latitude"), "longitude": item.get("longitude"),
            "floor_area_sqm": (float(item["squareFootage"]) * SQFT_TO_SQM) if item.get("squareFootage") else None,
            "land_area_sqm": (float(item["lotSize"]) * SQFT_TO_SQM) if item.get("lotSize") else None,
            "features": features, "listed_at": item.get("listedDate") or "", "fetched_at": utc_now_iso(),
            "parser_version": self.parser_version, "fetch_url": f"{self.base_url}{endpoint}",
            "source": {"mls_name": item.get("mlsName"), "mls_number": item.get("mlsNumber"), "days_on_market": item.get("daysOnMarket"), "listing_office": (item.get("listingOffice") or {}).get("name")},
        })

    def search(self, config: SearchConfig) -> Dict[str, Any]:
        properties: List[Dict[str, Any]] = []
        fetch_urls: List[str] = []
        try:
            key = self.api_key()
            for page in range(config.max_pages):
                url = self.build_url(config, page * 100)
                fetch_urls.append(url)
                rows = self.fetch(key, url)
                properties.extend(self.parse_listing(row, config.transaction) for row in rows)
                if len(rows) < 100:
                    break
        except Exception as exc:
            return {"portal": self.name, "provider": self.name, "country": "US", "fetched_at": utc_now_iso(), "count": len(properties), "fetch_urls": fetch_urls, "properties": properties, "error": str(exc)}
        return {"portal": self.name, "provider": self.name, "country": "US", "fetched_at": utc_now_iso(), "count": len(properties), "fetch_urls": fetch_urls, "properties": properties}

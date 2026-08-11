"""Domain adapter — Australia, official developer API."""

from __future__ import annotations

import json
import os
import subprocess
from typing import Any, Dict, List, Optional

from ..schema import normalise_listing, parse_price, utc_now_iso
from .base import PortalAdapter, SearchConfig

CITY_STATES = {"sydney": "NSW", "melbourne": "VIC", "brisbane": "QLD", "perth": "WA", "adelaide": "SA", "hobart": "TAS", "darwin": "NT", "canberra": "ACT"}


class DomainAdapter(PortalAdapter):
    name = "domain"
    parser_version = "domain-official-v1"
    search_endpoint = "https://api.domain.com.au/v1/listings/residential/_search"
    token_endpoint = "https://auth.domain.com.au/v1/connect/token"

    def credentials(self) -> tuple[str, str]:
        return os.environ.get("DOMAIN_CLIENT_ID", ""), os.environ.get("DOMAIN_CLIENT_SECRET", "")

    def token(self) -> str:
        client_id, secret = self.credentials()
        if not client_id or not secret:
            raise RuntimeError("Domain requires DOMAIN_CLIENT_ID and DOMAIN_CLIENT_SECRET from developer.domain.com.au")
        result = subprocess.run([
            "curl", "-sS", "--fail-with-body", "--max-time", "20",
            "-H", "Content-Type: application/x-www-form-urlencoded", "-d", f"client_id={client_id}",
            "-d", f"client_secret={secret}", "-d", "grant_type=client_credentials",
            "-d", "scope=api_listings_read", self.token_endpoint,
        ], capture_output=True, text=True, timeout=25)
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "Domain authentication failed")
        return json.loads(result.stdout)["access_token"]

    def build_payload(self, config: SearchConfig, page: int = 1) -> Dict[str, Any]:
        location = config.location.strip()
        bits = [bit.strip() for bit in location.split(",")]
        suburb = bits[0]
        state = str(config.extra.get("state") or (bits[1].upper() if len(bits) > 1 else CITY_STATES.get(suburb.lower(), "")))
        payload: Dict[str, Any] = {
            "listingType": "Rent" if config.transaction == "rent" else "Sale",
            "locations": [{"state": state, "suburb": suburb, "includeSurroundingSuburbs": bool(config.extra.get("surrounding", False))}],
            "pageNumber": page,
            "pageSize": 100,
        }
        if config.min_beds:
            payload["minBedrooms"] = config.min_beds
        if config.max_beds is not None:
            payload["maxBedrooms"] = config.max_beds
        if config.min_baths is not None:
            payload["minBathrooms"] = config.min_baths
        if config.min_price:
            payload["minPrice"] = int(config.min_price)
        if config.max_price:
            payload["maxPrice"] = int(config.max_price)
        if config.property_types:
            payload["propertyTypes"] = [item.strip() for item in config.property_types.split(",") if item.strip()]
        return payload

    def fetch(self, token: str, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        result = subprocess.run([
            "curl", "-sS", "--fail-with-body", "--max-time", "25", self.search_endpoint,
            "-H", f"Authorization: Bearer {token}", "-H", "Content-Type: application/json",
            "--data-binary", "@-",
        ], input=json.dumps(payload), capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "Domain search failed")
        return json.loads(result.stdout)

    def parse_listing(self, row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if row.get("type") != "PropertyListing" or not row.get("listing"):
            return None
        item = row["listing"]
        detail = item.get("propertyDetails") or {}
        price_data = item.get("priceDetails") or {}
        price_text = price_data.get("displayPrice") or "Price on application"
        price = price_data.get("price") or price_data.get("from") or parse_price(price_text)
        media = item.get("media") or []
        images = [entry.get("url") for entry in media if entry.get("category") == "Image" and entry.get("url")][:8]
        listing_id = str(item.get("id") or "")
        slug = item.get("listingSlug") or listing_id
        transaction = "rent" if str(item.get("listingType", "")).lower() == "rent" else "sale"
        return normalise_listing({
            "id": listing_id, "portal": self.name, "url": f"https://www.domain.com.au/{slug}",
            "address": detail.get("displayableAddress") or ", ".join(filter(None, [detail.get("streetNumber"), detail.get("street"), detail.get("suburb")])),
            "title": item.get("headline") or detail.get("displayableAddress") or "Property",
            "price": price, "price_text": price_text, "price_period": "week" if transaction == "rent" else "",
            "currency": "AUD", "country": "AU", "transaction": transaction,
            "beds": detail.get("bedrooms") or 0, "baths": detail.get("bathrooms") or 0,
            "property_type": detail.get("propertyType") or "property", "area": detail.get("suburb") or detail.get("area") or "",
            "postcode": detail.get("postcode") or "", "description": item.get("summaryDescription") or "",
            "images": images, "image_url": images[0] if images else "", "features": detail.get("features") or [],
            "latitude": detail.get("latitude"), "longitude": detail.get("longitude"), "land_area_sqm": detail.get("landArea"),
            "fetched_at": utc_now_iso(), "parser_version": self.parser_version, "fetch_url": self.search_endpoint,
            "source": {"state": detail.get("state"), "advertiser": (item.get("advertiser") or {}).get("name")},
        })

    def search(self, config: SearchConfig) -> Dict[str, Any]:
        properties: List[Dict[str, Any]] = []
        try:
            token = self.token()
            for page in range(1, config.max_pages + 1):
                rows = self.fetch(token, self.build_payload(config, page))
                parsed = [item for item in (self.parse_listing(row) for row in rows) if item]
                properties.extend(parsed)
                if len(rows) < 100:
                    break
        except Exception as exc:
            return {"portal": self.name, "provider": self.name, "country": "AU", "fetched_at": utc_now_iso(), "count": len(properties), "fetch_urls": [self.search_endpoint], "properties": properties, "error": str(exc)}
        return {"portal": self.name, "provider": self.name, "country": "AU", "fetched_at": utc_now_iso(), "count": len(properties), "fetch_urls": [self.search_endpoint], "properties": properties}

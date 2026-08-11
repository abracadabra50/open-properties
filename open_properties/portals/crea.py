"""CREA DDF adapter — official Canadian REALTOR.ca data-feed API."""

from __future__ import annotations

import json
import os
import subprocess
from typing import Any, Dict, List
from urllib.parse import urlencode

from ..schema import normalise_listing, utc_now_iso
from .base import PortalAdapter, SearchConfig

SQFT_TO_SQM = 0.09290304


class CREAAdapter(PortalAdapter):
    name = "crea-ddf"
    parser_version = "crea-ddf-odata-v1"
    token_endpoint = "https://identity.crea.ca/connect/token"
    property_endpoint = "https://ddfapi.realtor.ca/odata/v1/Property"

    def credentials(self) -> tuple[str, str]:
        return os.environ.get("CREA_DDF_CLIENT_ID", ""), os.environ.get("CREA_DDF_CLIENT_SECRET", "")

    def token(self) -> str:
        client_id, secret = self.credentials()
        if not client_id or not secret:
            raise RuntimeError("CREA DDF requires CREA_DDF_CLIENT_ID and CREA_DDF_CLIENT_SECRET from an active REALTOR.ca DDF data feed")
        result = subprocess.run([
            "curl", "-sS", "--fail-with-body", "--max-time", "20", self.token_endpoint,
            "-H", "Content-Type: application/x-www-form-urlencoded", "-d", "grant_type=client_credentials",
            "-d", f"client_id={client_id}", "-d", f"client_secret={secret}", "-d", "scope=DDFApi_Read",
        ], capture_output=True, text=True, timeout=25)
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "CREA DDF authentication failed")
        return json.loads(result.stdout)["access_token"]

    def build_url(self, config: SearchConfig, skip: int = 0) -> str:
        city = config.location.split(",", 1)[0].strip().replace("'", "''")
        price_field = "LeaseAmount" if config.transaction == "rent" else "ListPrice"
        filters = [f"City eq '{city}'", "LeaseAmount gt 0" if config.transaction == "rent" else "LeaseAmount eq null"]
        if config.min_price:
            filters.append(f"{price_field} ge {int(config.min_price)}")
        if config.max_price:
            filters.append(f"{price_field} le {int(config.max_price)}")
        if config.min_beds:
            filters.append(f"BedroomsTotal ge {config.min_beds}")
        if config.max_beds is not None:
            filters.append(f"BedroomsTotal le {config.max_beds}")
        fields = [
            "ListingKey", "ListingId", "ListingURL", "PropertySubType", "StructureType",
            "LeaseAmount", "LeaseAmountFrequency", "ListPrice", "PublicRemarks", "StandardStatus",
            "UnparsedAddress", "City", "CityRegion", "StateOrProvince", "PostalCode", "Latitude", "Longitude",
            "BedroomsTotal", "BathroomsTotalInteger", "BuildingAreaTotal", "BuildingAreaUnits",
            "BuildingFeatures", "OriginalEntryTimestamp", "ModificationTimestamp", "OriginatingSystemName", "Media",
        ]
        params = {"$filter": " and ".join(filters), "$select": ",".join(fields), "$top": 100, "$skip": skip}
        return f"{self.property_endpoint}?{urlencode(params)}"

    def fetch(self, token: str, url: str) -> List[Dict[str, Any]]:
        result = subprocess.run([
            "curl", "-sS", "--fail-with-body", "--max-time", "25", url,
            "-H", f"Authorization: Bearer {token}", "-H", "Accept: application/json",
        ], capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "CREA DDF property search failed")
        return json.loads(result.stdout).get("value") or []

    @staticmethod
    def _media_urls(item: Dict[str, Any]) -> List[str]:
        urls = []
        for media in item.get("Media") or []:
            url = media.get("MediaURL") or media.get("MediaURLLarge") or media.get("MediaURLFull") or media.get("URL")
            if url and url not in urls:
                urls.append(url)
        return urls[:8]

    def parse_listing(self, item: Dict[str, Any], transaction: str) -> Dict[str, Any]:
        price = item.get("LeaseAmount") if transaction == "rent" else item.get("ListPrice")
        price = price or 0
        units = str(item.get("BuildingAreaUnits") or "").lower()
        floor_area = item.get("BuildingAreaTotal")
        if floor_area and "feet" in units:
            floor_area = float(floor_area) * SQFT_TO_SQM
        images = self._media_urls(item)
        property_type = item.get("PropertySubType") or ((item.get("StructureType") or [""])[0] if isinstance(item.get("StructureType"), list) else item.get("StructureType")) or "property"
        return normalise_listing({
            "id": str(item.get("ListingKey") or item.get("ListingId") or ""), "portal": self.name,
            "url": item.get("ListingURL") or f"{self.property_endpoint}/{item.get('ListingKey', '')}",
            "address": item.get("UnparsedAddress") or ", ".join(filter(None, [item.get("City"), item.get("StateOrProvince"), item.get("PostalCode")])),
            "title": item.get("UnparsedAddress") or property_type, "price": price,
            "price_text": f"C${price:,.0f}" if price else "Price on application",
            "price_period": str(item.get("LeaseAmountFrequency") or "month").lower() if transaction == "rent" else "",
            "currency": "CAD", "country": "CA", "transaction": transaction,
            "beds": item.get("BedroomsTotal") or 0, "baths": item.get("BathroomsTotalInteger") or 0,
            "property_type": property_type, "area": item.get("CityRegion") or item.get("City") or "",
            "postcode": item.get("PostalCode") or "", "description": item.get("PublicRemarks") or "",
            "images": images, "image_url": images[0] if images else "", "features": item.get("BuildingFeatures") or [],
            "latitude": item.get("Latitude"), "longitude": item.get("Longitude"), "floor_area_sqm": floor_area,
            "listed_at": item.get("OriginalEntryTimestamp") or "", "fetched_at": utc_now_iso(),
            "parser_version": self.parser_version, "fetch_url": self.property_endpoint,
            "source": {"listing_id": item.get("ListingId"), "status": item.get("StandardStatus"), "originating_system": item.get("OriginatingSystemName")},
        })

    def search(self, config: SearchConfig) -> Dict[str, Any]:
        properties: List[Dict[str, Any]] = []
        fetch_urls: List[str] = []
        try:
            token = self.token()
            for page in range(config.max_pages):
                url = self.build_url(config, page * 100)
                fetch_urls.append(url)
                rows = self.fetch(token, url)
                properties.extend(self.parse_listing(row, config.transaction) for row in rows)
                if len(rows) < 100:
                    break
        except Exception as exc:
            return {"portal": self.name, "provider": self.name, "country": "CA", "fetched_at": utc_now_iso(), "count": len(properties), "fetch_urls": fetch_urls, "properties": properties, "error": str(exc)}
        return {"portal": self.name, "provider": self.name, "country": "CA", "fetched_at": utc_now_iso(), "count": len(properties), "fetch_urls": fetch_urls, "properties": properties}

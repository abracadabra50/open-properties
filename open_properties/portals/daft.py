"""Daft.ie adapter — Ireland, anonymous JSON API used by the web storefront."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import re
import subprocess
from typing import Any, Dict, List

from ..locations import resolve
from ..schema import normalise_listing, parse_price, utc_now_iso
from .base import PortalAdapter, SearchConfig


class DaftAdapter(PortalAdapter):
    name = "daft"
    parser_version = "daft-web-api-v2"
    endpoint = "https://gateway.daft.ie/api/v2/ads/listings"

    def build_payload(self, config: SearchConfig, offset: int = 0) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "section": "residential-to-rent" if config.transaction == "rent" else "residential-for-sale",
            "paging": {"from": str(offset), "pagesize": "50"},
        }
        location_id = config.location_id or resolve("daft", config.location)
        if location_id and location_id != "0":
            payload["geoFilter"] = {"storedShapeIds": [location_id], "geoSearchType": "STORED_SHAPES"}

        ranges = []
        if config.min_beds:
            ranges.append({"name": "numBeds", "from": str(config.min_beds), "to": str(config.max_beds or 1_000_000_000)})
        if config.min_baths:
            ranges.append({"name": "numBaths", "from": str(config.min_baths), "to": str(config.max_baths or 1_000_000_000)})
        price_name = "rentalPrice" if config.transaction == "rent" else "salePrice"
        if config.min_price or config.max_price:
            ranges.append({"name": price_name, "from": str(config.min_price or 0), "to": str(config.max_price or 1_000_000_000)})
        if ranges:
            payload["ranges"] = ranges
        return payload

    def fetch(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        result = subprocess.run(
            [
                "curl", "-sS", "--fail-with-body", "--max-time", "25", self.endpoint,
                "-H", "Content-Type: application/json", "-H", "brand: daft", "-H", "platform: web",
                "-H", "Origin: https://www.daft.ie", "-H", "Referer: https://www.daft.ie/",
                "-H", "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/135 Safari/537.36",
                "--data-binary", "@-",
            ],
            input=json.dumps(payload), capture_output=True, text=True, timeout=30,
        )
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "Daft request failed")
        return json.loads(result.stdout)

    def parse_listing(self, row: Dict[str, Any], fetch_url: str, transaction: str) -> Dict[str, Any]:
        item = row.get("listing") or row
        media = item.get("media") or {}
        images = [image.get("size720x480") or image.get("size680x392") for image in media.get("images", [])[:8]]
        images = [image for image in images if image]
        point = (item.get("point") or {}).get("coordinates") or []
        beds_match = re.search(r"\d+", str(item.get("numBedrooms") or ""))
        baths_match = re.search(r"\d+", str(item.get("numBathrooms") or ""))
        address = item.get("title") or item.get("seoTitle") or ""
        eircode = re.search(r"\b[A-Z]\d{2}\s?[A-Z0-9]{4}\b", address.upper())
        published = item.get("publishDate")
        listed_at = ""
        if isinstance(published, (int, float)):
            listed_at = datetime.fromtimestamp(published / 1000, tz=timezone.utc).isoformat()
        price_text = str(item.get("price") or "Price on application")
        path = item.get("seoFriendlyPath") or ""

        return normalise_listing({
            "id": str(item.get("id") or item.get("daftShortcode") or path),
            "portal": self.name,
            "url": f"https://www.daft.ie{path}" if path.startswith("/") else path,
            "address": address,
            "title": item.get("seoTitle") or address,
            "price": parse_price(price_text),
            "price_text": price_text,
            "price_period": "month" if transaction == "rent" else "",
            "currency": "EUR", "country": "IE", "transaction": transaction,
            "beds": int(beds_match.group()) if beds_match else 0,
            "baths": int(baths_match.group()) if baths_match else 0,
            "property_type": item.get("propertyType") or "property",
            "area": address.split(",")[-2].strip() if address.count(",") >= 1 else "",
            "postcode": eircode.group() if eircode else "",
            "images": images, "image_url": images[0] if images else "",
            "features": item.get("sections") or [],
            "latitude": point[1] if len(point) > 1 else None,
            "longitude": point[0] if len(point) > 1 else None,
            "listed_at": listed_at, "fetched_at": utc_now_iso(),
            "parser_version": self.parser_version, "fetch_url": fetch_url,
            "source": {"daft_shortcode": item.get("daftShortcode"), "sale_type": item.get("saleType")},
        })

    def search(self, config: SearchConfig) -> Dict[str, Any]:
        properties: List[Dict[str, Any]] = []
        fetch_urls = []
        total = None
        try:
            for page in range(config.max_pages):
                payload = self.build_payload(config, page * 50)
                fetch_urls.append(self.endpoint)
                body = self.fetch(payload)
                rows = body.get("listings") or []
                total = (body.get("paging") or {}).get("totalResults", total)
                properties.extend(self.parse_listing(row, self.endpoint, config.transaction) for row in rows)
                if len(rows) < 50:
                    break
        except Exception as exc:
            return {"portal": self.name, "provider": self.name, "country": "IE", "fetched_at": utc_now_iso(), "count": len(properties), "fetch_urls": fetch_urls or [self.endpoint], "properties": properties, "error": str(exc)}
        return {"portal": self.name, "provider": self.name, "country": "IE", "fetched_at": utc_now_iso(), "count": len(properties), "total_available": total, "fetch_urls": fetch_urls, "properties": properties}

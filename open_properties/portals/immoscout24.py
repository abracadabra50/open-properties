"""ImmoScout24 adapter — Germany via the anonymous mobile search API."""

from __future__ import annotations

import json
import re
import subprocess
from typing import Any, Dict, List
from urllib.parse import urlencode

from ..locations import resolve
from ..schema import normalise_listing, utc_now_iso
from .base import PortalAdapter, SearchConfig


class ImmoScout24Adapter(PortalAdapter):
    name = "immoscout24"
    parser_version = "immoscout-mobile-search-v1"
    endpoint = "https://api.mobile.immobilienscout24.de/search/list"
    user_agent = "ImmoScout_27.12_26.2_._"

    @staticmethod
    def real_estate_type(config: SearchConfig) -> str:
        is_house = "house" in (config.property_types or "").lower() or "haus" in (config.property_types or "").lower()
        if config.transaction == "rent":
            return "houserent" if is_house else "apartmentrent"
        return "housebuy" if is_house else "apartmentbuy"

    def build_url(self, config: SearchConfig, page: int = 1) -> str:
        geocode = config.location_id or resolve("immoscout24", config.location)
        if not str(geocode).startswith("/de/"):
            raise ValueError("ImmoScout24 needs a known city or --location-id '/de/state/city'")
        params: Dict[str, Any] = {
            "searchType": "region", "realestatetype": self.real_estate_type(config),
            "geocodes": geocode, "pagenumber": page,
        }
        if config.min_price or config.max_price:
            params["price"] = f"{config.min_price or ''}-{config.max_price or ''}"
        if config.min_rooms is not None or config.max_rooms is not None:
            params["numberofrooms"] = f"{config.min_rooms if config.min_rooms is not None else ''}-{config.max_rooms if config.max_rooms is not None else ''}"
        return f"{self.endpoint}?{urlencode(params)}"

    def fetch(self, url: str) -> Dict[str, Any]:
        result = subprocess.run([
            "curl", "-sS", "--fail-with-body", "--max-time", "25", "-X", "POST", url,
            "-H", f"User-Agent: {self.user_agent}", "-H", "Accept: application/json",
            "-H", "Content-Type: application/json", "--data-binary", '{"supportedResultListTypes":[],"userData":{}}',
        ], capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "ImmoScout24 search failed")
        return json.loads(result.stdout)

    @staticmethod
    def _localized_number(value: Any) -> float:
        text = re.sub(r"[^\d,.-]", "", str(value or ""))
        if "," in text:
            text = text.replace(".", "").replace(",", ".")
        elif re.match(r"^\d{1,3}(?:\.\d{3})+$", text):
            text = text.replace(".", "")
        try:
            return float(text)
        except ValueError:
            return 0.0

    def parse_listing(self, item: Dict[str, Any], transaction: str, fetch_url: str) -> Dict[str, Any]:
        attrs = item.get("attributes") or []
        price = self._localized_number(attrs[0].get("value")) if len(attrs) > 0 else 0
        area_sqm = self._localized_number(attrs[1].get("value")) if len(attrs) > 1 else 0
        rooms = self._localized_number(attrs[2].get("value")) if len(attrs) > 2 else 0
        address = item.get("address") or {}
        address_text = address.get("line") or ""
        postcode = re.search(r"\b\d{5}\b", address_text)
        title_picture = item.get("titlePicture") or {}
        images = [title_picture.get("full") or title_picture.get("preview")]
        for picture in item.get("pictures") or []:
            image = picture.get("url") or picture.get("urlScaleAndCrop")
            if image:
                images.append(image.replace("%WIDTH%", "800").replace("%HEIGHT%", "600"))
        images = list(dict.fromkeys(image for image in images if image))[:8]
        listing_id = str(item.get("id") or "")
        features = [tag.get("label") if isinstance(tag, dict) else tag for tag in item.get("tags") or []]
        features.extend(value for value in [item.get("energyEfficiencyClass"), "private offer" if item.get("isPrivate") else ""] if value)
        return normalise_listing({
            "id": listing_id, "portal": self.name, "url": f"https://www.immobilienscout24.de/expose/{listing_id}",
            "address": address_text, "title": item.get("title") or address_text or "Property",
            "price": price, "price_text": f"€{price:,.0f}" if price else "Price on application",
            "price_period": "month" if transaction == "rent" else "", "currency": "EUR", "country": "DE",
            "transaction": transaction, "beds": 0, "baths": 0, "rooms": rooms or None,
            "property_type": item.get("realEstateType") or "property", "area": address_text.split(",")[-1].strip() if "," in address_text else "",
            "postcode": postcode.group() if postcode else "", "images": images, "image_url": images[0] if images else "",
            "features": features, "latitude": address.get("lat"), "longitude": address.get("lon"),
            "floor_area_sqm": area_sqm or None, "fetched_at": utc_now_iso(), "parser_version": self.parser_version,
            "fetch_url": fetch_url, "source": {"listing_type": item.get("listingType"), "published": item.get("published"), "list_only_on_is24": item.get("listOnlyOnIs24")},
        })

    def search(self, config: SearchConfig) -> Dict[str, Any]:
        properties: List[Dict[str, Any]] = []
        fetch_urls: List[str] = []
        total = None
        try:
            for page in range(1, config.max_pages + 1):
                url = self.build_url(config, page)
                fetch_urls.append(url)
                body = self.fetch(url)
                total = body.get("totalResults", total)
                rows = [row.get("item") or {} for row in body.get("resultListItems") or [] if row.get("type") == "EXPOSE_RESULT"]
                properties.extend(self.parse_listing(row, config.transaction, url) for row in rows if row)
                if page >= int(body.get("numberOfPages") or page) or not rows:
                    break
        except Exception as exc:
            return {"portal": self.name, "provider": self.name, "country": "DE", "fetched_at": utc_now_iso(), "count": len(properties), "fetch_urls": fetch_urls, "properties": properties, "error": str(exc)}
        return {"portal": self.name, "provider": self.name, "country": "DE", "fetched_at": utc_now_iso(), "count": len(properties), "total_available": total, "fetch_urls": fetch_urls, "properties": properties}

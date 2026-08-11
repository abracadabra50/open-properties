"""Idealista adapter — official API for Spain, Italy and Portugal."""

from __future__ import annotations

import json
import os
import subprocess
from typing import Any, Dict, List

from ..locations import resolve
from ..schema import normalise_listing, utc_now_iso
from .base import PortalAdapter, SearchConfig

COUNTRY_CURRENCIES = {"ES": "EUR", "IT": "EUR", "PT": "EUR"}


class IdealistaAdapter(PortalAdapter):
    name = "idealista"
    parser_version = "idealista-official-3.5"
    token_endpoint = "https://api.idealista.com/oauth/token"

    def token(self) -> str:
        api_key = os.environ.get("IDEALISTA_API_KEY", "")
        secret = os.environ.get("IDEALISTA_API_SECRET", "")
        if not api_key or not secret:
            raise RuntimeError("Idealista requires IDEALISTA_API_KEY and IDEALISTA_API_SECRET from developers.idealista.com")
        result = subprocess.run([
            "curl", "-sS", "--fail-with-body", "--max-time", "20", "-u", f"{api_key}:{secret}",
            "-H", "Content-Type: application/x-www-form-urlencoded;charset=UTF-8",
            "-d", "grant_type=client_credentials", "-d", "scope=read", self.token_endpoint,
        ], capture_output=True, text=True, timeout=25)
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "Idealista authentication failed")
        return json.loads(result.stdout)["access_token"]

    def search_endpoint(self, country: str) -> str:
        return f"https://api.idealista.com/3.5/{country.lower()}/search"

    def build_fields(self, config: SearchConfig, page: int) -> Dict[str, str]:
        center = config.location_id or resolve("idealista", config.location)
        if "," not in center:
            raise ValueError("Idealista needs coordinates; use a known city or --location-id 'latitude,longitude'")
        fields = {
            "operation": config.transaction,
            "propertyType": config.extra.get("idealista_property_type", "homes"),
            "center": center,
            "distance": str(config.extra.get("distance_m", 20_000)),
            "maxItems": "50", "numPage": str(page), "order": "publicationDate", "sort": "desc",
        }
        if config.min_price:
            fields["minPrice"] = str(config.min_price)
        if config.max_price:
            fields["maxPrice"] = str(config.max_price)
        if config.min_beds:
            fields["bedrooms"] = str(config.min_beds)
        if config.min_baths:
            fields["bathrooms"] = str(config.min_baths)
        return fields

    def fetch(self, token: str, country: str, fields: Dict[str, str]) -> Dict[str, Any]:
        command = [
            "curl", "-sS", "--fail-with-body", "--max-time", "25", self.search_endpoint(country),
            "-H", f"Authorization: Bearer {token}", "-H", "Accept: application/json",
        ]
        for key, value in fields.items():
            command.extend(["-F", f"{key}={value}"])
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "Idealista search failed")
        return json.loads(result.stdout)

    def parse_listing(self, item: Dict[str, Any], country: str, transaction: str) -> Dict[str, Any]:
        image = item.get("thumbnail") or ""
        return normalise_listing({
            "id": str(item.get("propertyCode") or item.get("url") or ""),
            "portal": self.name, "url": item.get("url") or "", "address": item.get("address") or "",
            "title": item.get("description") or item.get("address") or "Property",
            "price": item.get("price") or 0, "price_text": item.get("priceInfo", {}).get("price", {}).get("amount") or "",
            "price_period": "month" if transaction == "rent" else "", "currency": COUNTRY_CURRENCIES[country],
            "country": country, "transaction": transaction, "beds": item.get("rooms") or 0,
            "baths": item.get("bathrooms") or 0, "property_type": item.get("propertyType") or "property",
            "area": item.get("municipality") or item.get("district") or item.get("province") or "",
            "description": item.get("description") or "", "images": [image] if image else [], "image_url": image,
            "features": [key for key in ["exterior" if item.get("exterior") else "", "new development" if item.get("newDevelopment") else "", item.get("status") or ""] if key],
            "latitude": item.get("latitude"), "longitude": item.get("longitude"), "floor_area_sqm": item.get("size"),
            "fetched_at": utc_now_iso(), "parser_version": self.parser_version, "fetch_url": self.search_endpoint(country),
            "source": {"province": item.get("province"), "district": item.get("district"), "neighborhood": item.get("neighborhood")},
        })

    def search(self, config: SearchConfig) -> Dict[str, Any]:
        country = config.country.upper()
        if country not in COUNTRY_CURRENCIES:
            return {"portal": self.name, "provider": self.name, "country": country, "fetched_at": utc_now_iso(), "count": 0, "properties": [], "error": "Idealista supports ES, IT and PT"}
        properties: List[Dict[str, Any]] = []
        endpoint = self.search_endpoint(country)
        try:
            token = self.token()
            total = None
            for page in range(1, config.max_pages + 1):
                body = self.fetch(token, country, self.build_fields(config, page))
                rows = body.get("elementList") or []
                total = body.get("total", total)
                properties.extend(self.parse_listing(row, country, config.transaction) for row in rows)
                if len(rows) < 50:
                    break
        except Exception as exc:
            return {"portal": self.name, "provider": self.name, "country": country, "fetched_at": utc_now_iso(), "count": len(properties), "fetch_urls": [endpoint], "properties": properties, "error": str(exc)}
        return {"portal": self.name, "provider": self.name, "country": country, "fetched_at": utc_now_iso(), "count": len(properties), "total_available": total, "fetch_urls": [endpoint], "properties": properties}

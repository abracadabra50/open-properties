"""International, dependency-free property listing schema."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import re

SCHEMA_VERSION = "property-listing.v1"
CURRENCY_SYMBOLS = {"GBP": "£", "EUR": "€", "USD": "$", "CAD": "C$", "AUD": "A$"}
COUNTRY_CURRENCIES = {"GB": "GBP", "IE": "EUR", "ES": "EUR", "IT": "EUR", "PT": "EUR", "US": "USD", "CA": "CAD", "AU": "AUD", "DE": "EUR"}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_price(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    text = str(value).strip()
    # Property prices are represented as whole currency units. Remove separators,
    # symbols and qualifiers while avoiding decimal-comma ambiguity.
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else 0


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def display_price(price: int, currency: str, fallback: str = "Price on application") -> str:
    if not price:
        return fallback
    return f"{CURRENCY_SYMBOLS.get(currency, currency + ' ')}{price:,}"


@dataclass
class PropertyListing:
    id: str
    portal: str
    url: str
    address: str
    price: int = 0
    currency: str = "GBP"
    country: str = "GB"
    transaction: str = "sale"
    price_text: str = "Price on application"
    price_period: str = ""
    beds: int = 0
    baths: int = 0
    title: str = "Property"
    property_type: str = "property"
    area: str = ""
    postcode: str = ""
    description: str = ""
    image_url: str = ""
    images: List[str] = field(default_factory=list)
    features: List[Any] = field(default_factory=list)
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    floor_area_sqm: Optional[float] = None
    land_area_sqm: Optional[float] = None
    listed_at: str = ""
    fetched_at: str = ""
    parser_version: str = ""
    fetch_url: str = ""
    source: Dict[str, Any] = field(default_factory=dict)
    confidence: Optional[float] = None
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        required = {"id", "portal", "url", "address", "price", "currency", "country", "transaction", "beds", "baths", "schema_version"}
        return {key: value for key, value in data.items() if value not in (None, "", [], {}) or key in required}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PropertyListing":
        images = data.get("images") or []
        if isinstance(images, str):
            images = [images]
        image_url = data.get("image_url") or (images[0] if images else "")
        country = clean_text(data.get("country") or "GB").upper()
        currency = clean_text(data.get("currency") or COUNTRY_CURRENCIES.get(country, "GBP")).upper()
        price = parse_price(data.get("price", 0))
        beds = int(data.get("beds") or 0)
        baths = int(data.get("baths") or 0)
        address = clean_text(data.get("address", ""))
        portal = clean_text(data.get("portal", "unknown")).lower()
        listing_id = clean_text(data.get("id") or data.get("listing_id") or data.get("url") or address)
        title = clean_text(data.get("title") or (f"{beds}-bed property" if beds else "Property"))

        return cls(
            id=listing_id,
            portal=portal,
            url=clean_text(data.get("url", "")),
            address=address,
            price=price,
            currency=currency,
            country=country,
            transaction=clean_text(data.get("transaction") or data.get("operation") or "sale").lower(),
            price_text=clean_text(data.get("price_text") or display_price(price, currency)),
            price_period=clean_text(data.get("price_period", "")),
            beds=beds,
            baths=baths,
            title=title,
            property_type=clean_text(data.get("property_type") or "property").lower(),
            area=clean_text(data.get("area", "")),
            postcode=clean_text(data.get("postcode", "")).upper(),
            description=clean_text(data.get("description", "")),
            image_url=str(image_url or ""),
            images=[str(image) for image in images if image],
            features=data.get("features") or [],
            latitude=_float_or_none(data.get("latitude")),
            longitude=_float_or_none(data.get("longitude")),
            floor_area_sqm=_float_or_none(data.get("floor_area_sqm")),
            land_area_sqm=_float_or_none(data.get("land_area_sqm")),
            listed_at=clean_text(data.get("listed_at", "")),
            fetched_at=clean_text(data.get("fetched_at", "")),
            parser_version=clean_text(data.get("parser_version", "")),
            fetch_url=clean_text(data.get("fetch_url", "")),
            source=data.get("source") or {},
            confidence=data.get("confidence"),
            schema_version=data.get("schema_version", SCHEMA_VERSION),
        )


def _float_or_none(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalise_listing(data: Dict[str, Any]) -> Dict[str, Any]:
    return PropertyListing.from_dict(data).to_dict()


def normalise_listings(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [normalise_listing(item) for item in items]

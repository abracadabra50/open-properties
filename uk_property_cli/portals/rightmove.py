"""Rightmove adapter."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

from ..locations import resolve
from ..schema import normalise_listing, utc_now_iso
from .base import PortalAdapter, SearchConfig

def categorize(price: int, beds: int) -> str:
    if price and price < 250000:
        return "investment"
    if beds >= 4:
        return "family"
    return "other"


class RightmoveAdapter(PortalAdapter):
    name = "rightmove"
    parser_version = "rightmove-nextjs-v2"

    def build_search_url(self, config: SearchConfig, index: int = 0, location_id: str = "") -> str:
        loc = (location_id or config.location_id or resolve("rightmove", config.location)).replace("^", "%5E")
        max_price = f"&maxPrice={config.max_price}" if config.max_price else ""
        property_types = f"&propertyTypes={config.property_types}" if config.property_types else ""
        return (
            "https://www.rightmove.co.uk/property-for-sale/find.html"
            f"?locationIdentifier={loc}&minBedrooms={config.min_beds}{max_price}{property_types}&sortType=6&index={index}"
        )

    def fetch(self, url: str) -> str:
        result = subprocess.run(
            [
                "curl", "-s", "--max-time", "15",
                "-H", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "-H", "Accept-Language: en-GB,en;q=0.9",
                url,
            ], capture_output=True, text=True, timeout=20
        )
        return result.stdout

    def extract_props_from_html(self, html: str) -> Tuple[List[Dict[str, Any]], int]:
        scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)
        for script in scripts:
            if "searchResults" not in script:
                continue
            try:
                data = json.loads(script)
                search_results = data["props"]["pageProps"]["searchResults"]
                return search_results.get("properties", []), search_results.get("resultCount", 0)
            except Exception:
                continue
        return [], 0

    def parse_property(self, prop: Dict[str, Any], fetch_url: str, location_id: str) -> Optional[Dict[str, Any]]:
        address = prop.get("displayAddress", "")

        price_data = prop.get("price") or {}
        price = price_data.get("amount", 0) or 0
        display_price = (price_data.get("displayPrices") or [{}])[0]
        qualifier = (display_price.get("displayPriceQualifier") or "").strip()
        raw_price = (display_price.get("displayPrice") or "").strip()
        price_text = f"{qualifier} {raw_price}".strip() if raw_price else (f"£{price:,}" if price else "Price on application")

        images = [img.get("srcUrl") for img in (prop.get("propertyImages") or {}).get("images", [])[:5] if img.get("srcUrl")]
        beds = prop.get("bedrooms", 0) or 0
        baths = prop.get("bathrooms", 0) or 0
        pc_match = re.search(r"\b((?:EH|KY|FK|G|ML|PA|KA|TD|DD|AB|IV|PH|KW|HS|ZE)\d+\s*\d*\w*)\b", address, re.I)

        return normalise_listing({
            "id": str(prop.get("id", "")),
            "title": prop.get("propertyTypeFullDescription", f"{beds}-bed property"),
            "price": price,
            "price_text": price_text,
            "beds": beds,
            "baths": baths,
            "property_type": (prop.get("propertySubType") or "property").lower(),
            "address": address,
            "area": address.split(",")[-1].strip() if "," in address else "",
            "postcode": pc_match.group(1).upper() if pc_match else "",
            "description": (prop.get("summary") or "")[:200],
            "url": f"https://www.rightmove.co.uk{prop.get('propertyUrl', '')}",
            "image_url": images[0] if images else "",
            "images": images,
            "features": prop.get("keyFeatures") or [],
            "portal": self.name,
            "category": categorize(price, beds),
            "fetched_at": utc_now_iso(),
            "parser_version": self.parser_version,
            "fetch_url": fetch_url,
            "source": {"search_location_identifier": location_id},
        })

    def search(self, config: SearchConfig) -> Dict[str, Any]:
        location_values = config.location_id or resolve("rightmove", config.location)
        location_ids = [x.strip() for x in location_values.split(",") if x.strip()]
        properties: List[Dict[str, Any]] = []
        seen_ids = set()
        fetch_urls = []

        for location_id in location_ids:
            for page_num in range(config.max_pages):
                index = page_num * 24
                url = self.build_search_url(config, index=index, location_id=location_id)
                fetch_urls.append(url)
                raw_properties, _ = self.extract_props_from_html(self.fetch(url))
                if not raw_properties:
                    break
                new_this_page = 0
                for raw in raw_properties:
                    parsed = self.parse_property(raw, url, location_id)
                    if parsed and parsed["id"] not in seen_ids:
                        seen_ids.add(parsed["id"])
                        properties.append(parsed)
                        new_this_page += 1
                if new_this_page == 0:
                    break

        return {"portal": self.name, "fetched_at": utc_now_iso(), "count": len(properties), "fetch_urls": fetch_urls, "properties": properties}


def legacy_main() -> None:
    beds = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    max_pages = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    location_id = sys.argv[3] if len(sys.argv) > 3 else "REGION^475"
    max_price = sys.argv[4] if len(sys.argv) > 4 else ""
    property_types = sys.argv[5] if len(sys.argv) > 5 else ""
    result = RightmoveAdapter().search(SearchConfig(min_beds=beds, max_pages=max_pages, location_id=location_id, max_price=max_price, property_types=property_types))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    legacy_main()

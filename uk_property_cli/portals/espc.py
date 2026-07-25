"""ESPC adapter."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from typing import Any, Dict, List

from ..locations import resolve
from ..schema import normalise_listing, parse_price, utc_now_iso
from .base import PortalAdapter, SearchConfig

def categorize(price: int, beds: int) -> str:
    if price and price < 250000:
        return "investment"
    if beds >= 4:
        return "family"
    return "other"


class ESPCAdapter(PortalAdapter):
    name = "espc"
    parser_version = "espc-html-v2"

    def build_search_url(self, config: SearchConfig) -> str:
        location = resolve("espc", config.location)
        kind = "flats" if "flat" in (config.property_types or "").lower() else "houses"
        return f"https://espc.com/property-for-sale/{location}/{kind}/{config.min_beds}-bed?sort=date-desc"

    def fetch(self, url: str) -> str:
        result = subprocess.run(["curl", "-s", "--max-time", "15", "-H", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)", url], capture_output=True, text=True, timeout=20)
        return result.stdout

    def parse_properties(self, html: str, config: SearchConfig, fetch_url: str) -> List[Dict[str, Any]]:
        properties = []
        property_ids = list(dict.fromkeys(re.findall(r'id="property-(\d+)-', html)))
        for prop_id in property_ids[: config.max_pages * 20]:
            match = re.search(rf'id="property-{prop_id}-.*?(?=id="property-\d+|class="pageWrap"|$)', html, re.DOTALL)
            if not match:
                continue
            section = match.group(0)
            url_match = re.search(r'href="(/property/([^"]+))"', section)
            if not url_match:
                continue
            url_path = url_match.group(1)
            address_slug = url_match.group(2).split('/')[0]
            address = address_slug.replace('-', ' ').title()
            address = re.sub(r' Eh(\d+)', r', EH\1', address)

            price = 0
            price_text = "Price on application"
            price_match = re.search(r'(Offers Over|Fixed Price|Offers From).*?£([\d,]+)', section, re.DOTALL)
            if price_match:
                price_text = f"{price_match.group(1)} £{price_match.group(2)}"
                price = parse_price(price_match.group(2))

            beds = int(config.min_beds or 0)
            beds_match = re.search(r'(\d+)\s+bed', section, re.IGNORECASE)
            if beds_match:
                beds = int(beds_match.group(1))
            baths = 0
            baths_match = re.search(r'(\d+)\s+bath', section, re.IGNORECASE)
            if baths_match:
                baths = int(baths_match.group(1))
            img_match = re.search(r'data-src="([^"]+)"', section)
            image_url = img_match.group(1) if img_match else ""
            pc_match = re.search(r'(EH\d+\s*\d*\w*)', address.upper())

            properties.append(normalise_listing({
                "id": prop_id,
                "title": f"{beds}-bed property" if beds else "Property",
                "price": price,
                "price_text": price_text,
                "beds": beds,
                "baths": baths,
                "property_type": "flat" if "flat" in (config.property_types or "").lower() else "house",
                "address": address,
                "area": address.split(',')[-1].strip() if ',' in address else address.split()[-1],
                "postcode": pc_match.group(1) if pc_match else "",
                "url": f"https://espc.com{url_path.split('?')[0]}",
                "image_url": image_url,
                "images": [image_url] if image_url else [],
                "portal": self.name,
                "category": categorize(price, beds),
                "fetched_at": utc_now_iso(),
                "parser_version": self.parser_version,
                "fetch_url": fetch_url,
            }))
        return properties

    def search(self, config: SearchConfig) -> Dict[str, Any]:
        url = self.build_search_url(config)
        properties = self.parse_properties(self.fetch(url), config, url)
        return {"portal": self.name, "fetched_at": utc_now_iso(), "count": len(properties), "fetch_urls": [url], "properties": properties}


def legacy_main() -> None:
    beds = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    result = ESPCAdapter().search(SearchConfig(min_beds=beds))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    legacy_main()

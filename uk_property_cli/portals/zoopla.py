"""Zoopla adapter. Uses Firecrawl CLI when available."""

from __future__ import annotations

import json
import re
import shutil
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


class ZooplaAdapter(PortalAdapter):
    name = "zoopla"
    parser_version = "zoopla-firecrawl-v2"

    def build_search_url(self, config: SearchConfig) -> str:
        location = resolve("zoopla", config.location)
        max_price = f"&price_max={config.max_price}" if config.max_price else ""
        return f"https://www.zoopla.co.uk/for-sale/property/{location}/?beds_min={config.min_beds}{max_price}&results_sort=newest_listings"

    def fetch(self, url: str) -> str:
        if not shutil.which("firecrawl"):
            return ""
        result = subprocess.run(["firecrawl", "scrape", url, "--format", "markdown"], capture_output=True, text=True, timeout=45)
        return result.stdout

    def parse_properties(self, markdown: str, fetch_url: str) -> List[Dict[str, Any]]:
        properties = []
        property_pattern = r'\[£([\d,]+).*?(\d+)\s+beds?.*?(\d+)\s+baths?.*?\n(.*?)\n(.*?)\]'
        for price_text, beds, baths, address, description in re.findall(property_pattern, markdown, re.DOTALL | re.IGNORECASE):
            price = parse_price(price_text)
            pc_match = re.search(r'(EH\d+\s*\d*\w*)', address.upper())
            prop_id = str(abs(hash(address)) % 100000000)
            properties.append(normalise_listing({
                "id": prop_id,
                "title": f"{beds}-bed property",
                "price": price,
                "price_text": f"£{price_text}",
                "beds": int(beds),
                "baths": int(baths),
                "property_type": "property",
                "address": address.strip(),
                "area": address.split(',')[-1].strip() if ',' in address else "",
                "postcode": pc_match.group(1) if pc_match else "",
                "description": description.strip()[:200],
                "url": f"https://www.zoopla.co.uk/for-sale/details/{prop_id}/",
                "portal": self.name,
                "category": categorize(price, int(beds)),
                "fetched_at": utc_now_iso(),
                "parser_version": self.parser_version,
                "fetch_url": fetch_url,
            }))
        return properties

    def search(self, config: SearchConfig) -> Dict[str, Any]:
        url = self.build_search_url(config)
        markdown = self.fetch(url)
        if not markdown:
            return {"portal": self.name, "fetched_at": utc_now_iso(), "count": 0, "fetch_urls": [url], "properties": [], "error": "Firecrawl CLI not available or API key not set"}
        properties = self.parse_properties(markdown, url)
        return {"portal": self.name, "fetched_at": utc_now_iso(), "count": len(properties), "fetch_urls": [url], "properties": properties, "note": "Uses Firecrawl CLI/API"}


def legacy_main() -> None:
    beds = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    result = ZooplaAdapter().search(SearchConfig(min_beds=beds))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    legacy_main()

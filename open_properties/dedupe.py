"""Deduplicate property listings with confidence scores and candidate reporting."""

from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from typing import Any, Dict, List, Tuple

from .schema import display_price

STREET_SUFFIXES = {
    "st", "street", "rd", "road", "ave", "avenue", "dr", "drive", "crescent",
    "place", "terrace", "gardens", "garden", "lane", "court", "way", "close",
    "park", "view", "walk", "mews", "square", "loan", "riggs", "brae",
    "strasse", "straße", "calle", "carrer", "rua", "rue", "via", "viale",
}

LOCATION_WORDS = {
    "edinburgh", "glasgow", "fife", "kirkcaldy", "dunfermline", "leven", "rosyth",
    "cowdenbeath", "falkland", "dalkeith", "bonnyrigg", "midlothian", "lothian",
    "east", "west", "north", "south", "scotland", "shire", "county",
}


def normalize_address(addr: str) -> str:
    addr = (addr or "").lower()
    addr = addr.replace(",", "").replace(".", "")
    addr = addr.replace(" street", " st").replace(" road", " rd")
    addr = addr.replace(" avenue", " ave").replace(" drive", " dr")
    return " ".join(addr.split())


def postcode_sector(addr: str) -> str:
    match = re.search(r"\b([A-Z]{1,2}\d{1,2})\s*(\d)?", (addr or "").upper())
    if not match:
        return ""
    return f"{match.group(1)} {match.group(2) or ''}".strip()


def street_tokens(addr: str) -> set:
    first_part = (addr or "").split(",", 1)[0].lower()
    tokens = re.findall(r"[a-z]+", first_part)
    return {
        token for token in tokens
        if len(token) > 2
        and token not in STREET_SUFFIXES
        and token not in LOCATION_WORDS
        and not re.match(r"^[a-z]{1,2}\d*$", token)
    }


def addresses_match(addr1: str, addr2: str, threshold: float = 0.85) -> bool:
    """Address-only compatibility helper.

    Looser than full property dedupe because it has no portal IDs, price or bed
    evidence. Full duplicate decisions should use match_confidence/properties_match.
    """
    norm1 = normalize_address(addr1)
    norm2 = normalize_address(addr2)
    similarity = SequenceMatcher(None, norm1, norm2).ratio() if norm1 and norm2 else 0.0
    tokens1, tokens2 = street_tokens(addr1), street_tokens(addr2)

    if similarity >= threshold:
        return not (tokens1 and tokens2 and tokens1.isdisjoint(tokens2))

    return similarity >= 0.80 and bool(tokens1 and tokens2 and not tokens1.isdisjoint(tokens2))


def same_portal_identity(prop1: Dict[str, Any], prop2: Dict[str, Any]) -> bool:
    if prop1.get("portal") != prop2.get("portal"):
        return False
    id1, id2 = str(prop1.get("id") or ""), str(prop2.get("id") or "")
    if id1 and id2 and id1 == id2:
        return True
    url1, url2 = prop1.get("url") or "", prop2.get("url") or ""
    return bool(url1 and url2 and url1 == url2)


def match_confidence(prop1: Dict[str, Any], prop2: Dict[str, Any]) -> Tuple[float, List[str]]:
    """Return duplicate confidence and human-readable evidence."""
    reasons: List[str] = []

    country1, country2 = str(prop1.get("country") or "").upper(), str(prop2.get("country") or "").upper()
    if country1 and country2 and country1 != country2:
        return 0.0, ["different countries"]

    currency1, currency2 = str(prop1.get("currency") or "").upper(), str(prop2.get("currency") or "").upper()
    if currency1 and currency2 and currency1 != currency2:
        return 0.0, ["different currencies"]

    if prop1.get("portal") == prop2.get("portal"):
        if same_portal_identity(prop1, prop2):
            return 1.0, ["same portal id/url"]
        return 0.0, ["same portal but different id/url"]

    addr1, addr2 = prop1.get("address", ""), prop2.get("address", "")
    norm1, norm2 = normalize_address(addr1), normalize_address(addr2)
    similarity = SequenceMatcher(None, norm1, norm2).ratio() if norm1 and norm2 else 0.0
    score = similarity * 0.45
    reasons.append(f"address similarity {similarity:.2f}")

    tokens1, tokens2 = street_tokens(addr1), street_tokens(addr2)
    if tokens1 and tokens2 and not tokens1.isdisjoint(tokens2):
        score += 0.25
        reasons.append("street tokens overlap")
    elif tokens1 and tokens2:
        score -= 0.25
        reasons.append("different street tokens")

    postal1 = str(prop1.get("postcode") or "").replace(" ", "").upper()
    postal2 = str(prop2.get("postcode") or "").replace(" ", "").upper()
    if postal1 and postal2 and postal1 == postal2:
        score += 0.15
        reasons.append("same postal code")
    elif postal1 and postal2:
        score -= 0.05
        reasons.append("different postal code")
    else:
        sector1, sector2 = postcode_sector(addr1), postcode_sector(addr2)
        if sector1 and sector2 and sector1 == sector2:
            score += 0.15
            reasons.append("same postcode sector")

    beds1, beds2 = int(prop1.get("beds") or 0), int(prop2.get("beds") or 0)
    if beds1 and beds2 and beds1 == beds2:
        score += 0.08
        reasons.append("same bedroom count")

    price1, price2 = int(prop1.get("price") or 0), int(prop2.get("price") or 0)
    if price1 and price2:
        gap = abs(price1 - price2) / max(price1, price2)
        if gap <= 0.03:
            score += 0.07
            reasons.append("price within 3%")
        elif gap > 0.20:
            score -= 0.07
            reasons.append("price differs by >20%")

    return max(0.0, min(1.0, score)), reasons


def properties_match(prop1: Dict[str, Any], prop2: Dict[str, Any], threshold: float = 0.88) -> bool:
    return match_confidence(prop1, prop2)[0] >= threshold


def merge_property_data(duplicates: List[Dict[str, Any]]) -> Dict[str, Any]:
    merged = duplicates[0].copy()

    all_images, seen_images = [], set()
    for prop in duplicates:
        for image in prop.get("images", []):
            if image and image not in seen_images:
                seen_images.add(image)
                all_images.append(image)
    merged["images"] = all_images

    prices = [p["price"] for p in duplicates if p.get("price", 0) > 0]
    if prices:
        merged["price"] = min(prices)
        currency = str(merged.get("currency") or "GBP")
        merged["price_text"] = display_price(min(prices), currency)

    merged["beds"] = max(p.get("beds", 0) for p in duplicates)
    merged["baths"] = max(p.get("baths", 0) for p in duplicates)
    merged["portals"] = [p.get("portal") for p in duplicates]
    merged["urls"] = {p.get("portal"): p.get("url") for p in duplicates if p.get("portal") and p.get("url")}

    image_urls = [p.get("image_url", "") for p in duplicates if p.get("image_url")]
    if image_urls:
        merged["image_url"] = image_urls[0]

    all_features, seen_features = [], set()
    for prop in duplicates:
        for feature in prop.get("features", []):
            key = json.dumps(feature, sort_keys=True) if isinstance(feature, dict) else str(feature)
            if key not in seen_features:
                seen_features.add(key)
                all_features.append(feature)
    merged["features"] = all_features

    descriptions = [p.get("description", "") for p in duplicates]
    merged["description"] = max(descriptions, key=len) if descriptions else ""
    merged["dedupe"] = {
        "merged_count": len(duplicates),
        "source_ids": [f"{p.get('portal')}:{p.get('id')}" for p in duplicates],
    }
    return merged


def deduplicate_with_report(properties: List[Dict[str, Any]], threshold: float = 0.88, candidate_threshold: float = 0.72) -> Dict[str, Any]:
    unique: List[Dict[str, Any]] = []
    processed = set()
    candidates: List[Dict[str, Any]] = []

    for i, prop in enumerate(properties):
        if i in processed:
            continue
        duplicates = [prop]
        processed.add(i)

        for j, other in enumerate(properties[i + 1 :], start=i + 1):
            if j in processed:
                continue
            score, reasons = match_confidence(prop, other)
            if score >= candidate_threshold:
                candidates.append({
                    "left": f"{prop.get('portal')}:{prop.get('id')}",
                    "right": f"{other.get('portal')}:{other.get('id')}",
                    "score": round(score, 3),
                    "reasons": reasons,
                    "merged": score >= threshold,
                })
            if score >= threshold:
                duplicates.append(other)
                processed.add(j)

        unique.append(merge_property_data(duplicates) if len(duplicates) > 1 else prop)

    return {
        "deduplication": {
            "original_count": len(properties),
            "unique_count": len(unique),
            "duplicate_count": len(properties) - len(unique),
            "duplicate_percentage": round(((len(properties) - len(unique)) / len(properties)) * 100, 1) if properties else 0,
            "threshold": threshold,
            "candidate_threshold": candidate_threshold,
        },
        "duplicate_candidates": candidates,
        "properties": unique,
    }


def deduplicate(properties: List[Dict[str, Any]], threshold: float = 0.88) -> List[Dict[str, Any]]:
    return deduplicate_with_report(properties, threshold=threshold)["properties"]

"""Optional scoring/ranking layer. Scrapers stay dumb; profiles define taste."""

from __future__ import annotations

from typing import Any, Dict, List


def score_property(prop: Dict[str, Any], profile: Dict[str, Any]) -> Dict[str, Any]:
    scoring = profile.get("scoring", {})
    areas = profile.get("areas", {})
    score = 0
    reasons: List[str] = []
    address = (prop.get("address", "") + " " + prop.get("postcode", "")).lower()

    for area in areas.get("premium", []):
        if area.lower() in address:
            weight = scoring.get("area_weights", {}).get("premium", 30)
            score += weight
            reasons.append(f"premium area +{weight}")
            break

    price = int(prop.get("price") or 0)
    ideal_min = scoring.get("price_ideal_min")
    ideal_max = scoring.get("price_ideal_max")
    if price and ideal_min and ideal_max and ideal_min <= price <= ideal_max:
        score += 15
        reasons.append("inside ideal price band +15")

    if scoring.get("prefer_images", True) and prop.get("images"):
        score += 5
        reasons.append("has images +5")

    if scoring.get("prefer_multiple_portals", True) and len(prop.get("portals", [])) > 1:
        score += 10
        reasons.append("seen on multiple portals +10")

    ranked = dict(prop)
    ranked["score"] = score
    ranked["score_reasons"] = reasons
    return ranked


def rank_properties(properties: List[Dict[str, Any]], profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    return sorted((score_property(p, profile) for p in properties), key=lambda p: p.get("score", 0), reverse=True)

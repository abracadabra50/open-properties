"""Filtering with explainable removal reasons."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


def _contains_any(prop: Dict[str, Any], needles: List[str]) -> bool:
    hay = " ".join(str(prop.get(k, "")) for k in ["address", "postcode", "area"]).lower()
    return any(n.lower() in hay for n in needles if n)


def removal_reasons(
    prop: Dict[str, Any],
    areas: Optional[List[str]] = None,
    exclude: Optional[List[str]] = None,
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
    min_beds: Optional[int] = None,
    max_beds: Optional[int] = None,
    category: Optional[str] = None,
) -> List[str]:
    reasons = []
    if areas and not _contains_any(prop, areas):
        reasons.append(f"outside desired areas: {', '.join(areas)}")
    if exclude and _contains_any(prop, exclude):
        reasons.append(f"excluded area match: {', '.join(exclude)}")
    price = int(prop.get("price") or 0)
    if min_price is not None and price < min_price:
        reasons.append(f"price below min: {price} < {min_price}")
    if max_price is not None and price > max_price:
        reasons.append(f"price above max: {price} > {max_price}")
    beds = int(prop.get("beds") or 0)
    if min_beds is not None and beds < min_beds:
        reasons.append(f"beds below min: {beds} < {min_beds}")
    if max_beds is not None and beds > max_beds:
        reasons.append(f"beds above max: {beds} > {max_beds}")
    if category and prop.get("category") != category:
        reasons.append(f"category mismatch: {prop.get('category')} != {category}")
    return reasons


def filter_properties_with_reasons(properties: List[Dict[str, Any]], **criteria: Any) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    kept, removed = [], []
    for prop in properties:
        reasons = removal_reasons(prop, **criteria)
        if reasons:
            item = dict(prop)
            item["filter_reasons"] = reasons
            removed.append(item)
        else:
            kept.append(prop)
    return kept, removed


def filter_properties(properties: List[Dict[str, Any]], **criteria: Any) -> List[Dict[str, Any]]:
    kept, _ = filter_properties_with_reasons(properties, **criteria)
    return kept

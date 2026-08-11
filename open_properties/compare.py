"""Snapshot comparison."""

from __future__ import annotations

from typing import Any, Dict, List


def property_key(prop: Dict[str, Any]) -> str:
    if prop.get("urls"):
        return "|".join(f"{k}:{v}" for k, v in sorted(prop["urls"].items()))
    if prop.get("portal") and prop.get("id"):
        return f"{prop['portal']}:{prop['id']}"
    return prop.get("url") or prop.get("address") or str(id(prop))


def compare_snapshots(old: List[Dict[str, Any]], new: List[Dict[str, Any]]) -> Dict[str, Any]:
    old_by_key = {property_key(p): p for p in old}
    new_by_key = {property_key(p): p for p in new}

    new_keys = set(new_by_key) - set(old_by_key)
    removed_keys = set(old_by_key) - set(new_by_key)

    price_changes = []
    for key in set(old_by_key) & set(new_by_key):
        before, after = old_by_key[key], new_by_key[key]
        old_price, new_price = int(before.get("price") or 0), int(after.get("price") or 0)
        if old_price > 0 and new_price > 0 and old_price != new_price:
            price_changes.append({
                "property": after,
                "old_price": old_price,
                "new_price": new_price,
                "change": new_price - old_price,
                "change_percent": round(((new_price - old_price) / old_price) * 100, 1),
            })

    price_changes.sort(key=lambda item: item["change_percent"])
    return {
        "new_listings": [new_by_key[k] for k in sorted(new_keys)],
        "removed_listings": [old_by_key[k] for k in sorted(removed_keys)],
        "price_changes": price_changes,
        "stats": {
            "new_count": len(new_keys),
            "removed_count": len(removed_keys),
            "price_changes_count": len(price_changes),
            "price_drops": len([c for c in price_changes if c["change"] < 0]),
            "price_increases": len([c for c in price_changes if c["change"] > 0]),
        },
    }

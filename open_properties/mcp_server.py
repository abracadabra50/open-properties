"""Dependency-free MCP stdio server for open-properties."""

from __future__ import annotations

import json
import sys
from typing import Any, Dict, List, Optional

from . import __version__
from .compare import compare_snapshots
from .config import load_profile
from .dedupe import deduplicate_with_report
from .filters import filter_properties_with_reasons
from .locations import find as find_locations
from .portals.base import SearchConfig
from .providers import ADAPTERS, PROVIDERS, list_providers, provider_ids_for, validate_provider
from .schema import utc_now_iso
from .scoring import rank_properties

JsonDict = Dict[str, Any]
COUNTRY_DEFAULT_LOCATIONS = {"GB": "edinburgh", "IE": "dublin", "AU": "sydney", "ES": "madrid", "IT": "rome", "PT": "lisbon"}


def _int_or_none(value: Any) -> Optional[int]:
    return None if value in (None, "", "none", "null") else int(value)


def _csv(value: Any) -> Optional[List[str]]:
    if value in (None, ""):
        return None
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    return [item.strip() for item in str(value).split(",") if item.strip()]


def search_properties(arguments: JsonDict) -> JsonDict:
    profile = load_profile(arguments.get("profile", "")) if arguments.get("profile") else load_profile("")
    search = profile.get("search", {})
    country = (arguments.get("country") or search.get("country") or "GB").upper()
    profile_location = search.get("location") if arguments.get("profile") else None
    config = SearchConfig(
        country=country,
        transaction=arguments.get("transaction") or search.get("transaction") or "sale",
        min_beds=int(arguments.get("min_beds") if arguments.get("min_beds") is not None else (search.get("min_beds") or 1)),
        max_beds=_int_or_none(arguments.get("max_beds")), min_baths=_int_or_none(arguments.get("min_baths")),
        max_baths=_int_or_none(arguments.get("max_baths")), min_price=str(arguments.get("min_price") or ""),
        max_price=str(arguments.get("max_price") or search.get("max_price") or ""),
        property_types=arguments.get("property_types") or ",".join(search.get("property_types") or []),
        location=arguments.get("location") or profile_location or COUNTRY_DEFAULT_LOCATIONS.get(country, ""),
        location_id=arguments.get("location_id") or "", max_pages=int(arguments.get("max_pages") or 3),
        extra={"state": arguments.get("state", ""), "distance_m": arguments.get("distance", 20_000), "surrounding": arguments.get("surrounding", False)},
    )
    requested = arguments.get("provider") or arguments.get("portal") or "all"
    providers = provider_ids_for(config.country, config.transaction) if requested == "all" else [requested]
    if not providers:
        raise ValueError(f"No providers support {config.transaction} listings in {config.country}")
    for provider in providers:
        validate_provider(provider, config.country, config.transaction)

    all_properties: List[JsonDict] = []
    provider_results = []
    for provider in providers:
        try:
            item = ADAPTERS[provider]().search(config)
        except Exception as exc:
            item = {"portal": provider, "provider": provider, "country": config.country, "count": 0, "properties": [], "error": str(exc)}
        provider_results.append({key: value for key, value in item.items() if key != "properties"})
        all_properties.extend(item.get("properties", []))

    result: JsonDict = {
        "tool": "open-properties-mcp", "version": __version__, "fetched_at": utc_now_iso(), "query": arguments,
        "resolved_search": {"country": config.country, "transaction": config.transaction, "location": config.location, "providers": providers},
        "provider_results": provider_results, "portal_results": provider_results,
        "count": len(all_properties), "properties": all_properties,
    }
    if arguments.get("dedupe") or profile.get("deduplication", {}).get("enabled"):
        dconf = profile.get("deduplication", {})
        result.update(deduplicate_with_report(
            result["properties"], threshold=float(arguments.get("dedupe_threshold") or dconf.get("threshold", 0.88)),
            candidate_threshold=float(arguments.get("candidate_threshold") or dconf.get("candidate_threshold", 0.72)),
        ))
        result["count"] = len(result["properties"])
    if arguments.get("apply_filters"):
        kept, removed = filter_properties_with_reasons(
            result["properties"], areas=_csv(arguments.get("areas")) or profile.get("areas", {}).get("desired") or None,
            exclude=_csv(arguments.get("exclude")) or profile.get("areas", {}).get("excluded") or None,
            min_price=_int_or_none(arguments.get("min_price")), max_price=_int_or_none(arguments.get("max_price")),
            min_beds=_int_or_none(arguments.get("min_beds")), max_beds=_int_or_none(arguments.get("max_beds")), category=arguments.get("category"),
        )
        result["filtering"] = {"original_count": len(result["properties"]), "filtered_count": len(kept), "removed_count": len(removed)}
        if arguments.get("explain"):
            result["removed_properties"] = removed
        result["properties"] = kept; result["count"] = len(kept)
    if arguments.get("rank"):
        result["properties"] = rank_properties(result["properties"], profile)
    return result


def providers_tool(arguments: JsonDict) -> JsonDict:
    rows = list_providers(arguments.get("country", ""))
    return {"count": len(rows), "providers": rows}


def locations_tool(arguments: JsonDict) -> JsonDict:
    return {"locations": find_locations(arguments.get("query", ""), arguments.get("country", ""))}


def dedupe_tool(arguments: JsonDict) -> JsonDict:
    properties = arguments.get("properties") or []
    if not isinstance(properties, list): raise ValueError("properties must be a list")
    return deduplicate_with_report(properties, float(arguments.get("threshold", 0.88)), float(arguments.get("candidate_threshold", 0.72)))


def filter_tool(arguments: JsonDict) -> JsonDict:
    properties = arguments.get("properties") or []
    if not isinstance(properties, list): raise ValueError("properties must be a list")
    kept, removed = filter_properties_with_reasons(
        properties, areas=_csv(arguments.get("areas")), exclude=_csv(arguments.get("exclude")),
        min_price=_int_or_none(arguments.get("min_price")), max_price=_int_or_none(arguments.get("max_price")),
        min_beds=_int_or_none(arguments.get("min_beds")), max_beds=_int_or_none(arguments.get("max_beds")), category=arguments.get("category"),
    )
    result: JsonDict = {"filtering": {"original_count": len(properties), "filtered_count": len(kept), "removed_count": len(removed)}, "properties": kept}
    if arguments.get("explain"): result["removed_properties"] = removed
    return result


def compare_tool(arguments: JsonDict) -> JsonDict:
    old, new = arguments.get("old_properties") or [], arguments.get("new_properties") or []
    if not isinstance(old, list) or not isinstance(new, list): raise ValueError("old_properties and new_properties must be lists")
    return compare_snapshots(old, new)


SEARCH_SCHEMA = {
    "type": "object", "properties": {
        "provider": {"type": "string", "enum": ["all", *PROVIDERS], "default": "all"},
        "country": {"type": "string", "default": "GB", "description": "ISO country code"},
        "transaction": {"type": "string", "enum": ["sale", "rent"], "default": "sale"},
        "location": {"type": "string"}, "location_id": {"type": "string"}, "state": {"type": "string"},
        "min_beds": {"type": "integer"}, "max_beds": {"type": "integer"}, "min_baths": {"type": "integer"},
        "max_baths": {"type": "integer"}, "min_price": {"type": "integer"}, "max_price": {"type": "integer"},
        "property_types": {"type": "string"}, "max_pages": {"type": "integer", "default": 3},
        "dedupe": {"type": "boolean"}, "apply_filters": {"type": "boolean"}, "areas": {"type": "string"},
        "exclude": {"type": "string"}, "explain": {"type": "boolean"}, "rank": {"type": "boolean"}, "profile": {"type": "string"},
    }, "required": ["location"],
}

TOOLS: Dict[str, Dict[str, Any]] = {
    "property_search": {"description": "Search property providers by country and return normalized property-listing.v1 JSON.", "handler": search_properties, "inputSchema": SEARCH_SCHEMA},
    "property_providers": {"description": "List available providers, countries, transactions and authentication requirements.", "handler": providers_tool, "inputSchema": {"type": "object", "properties": {"country": {"type": "string"}}}},
    "property_locations": {"description": "Find known provider location IDs or coordinate shortcuts.", "handler": locations_tool, "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "country": {"type": "string"}}}},
    "property_dedupe": {"description": "Deduplicate normalized property listings conservatively.", "handler": dedupe_tool, "inputSchema": {"type": "object", "properties": {"properties": {"type": "array"}, "threshold": {"type": "number"}, "candidate_threshold": {"type": "number"}}, "required": ["properties"]}},
    "property_filter": {"description": "Filter property listings and optionally explain removals.", "handler": filter_tool, "inputSchema": {"type": "object", "properties": {"properties": {"type": "array"}, "areas": {"type": "string"}, "exclude": {"type": "string"}, "min_price": {"type": "integer"}, "max_price": {"type": "integer"}, "min_beds": {"type": "integer"}, "max_beds": {"type": "integer"}, "explain": {"type": "boolean"}}, "required": ["properties"]}},
    "property_compare": {"description": "Compare two snapshots for new, removed and price-changed listings.", "handler": compare_tool, "inputSchema": {"type": "object", "properties": {"old_properties": {"type": "array"}, "new_properties": {"type": "array"}}, "required": ["old_properties", "new_properties"]}},
}

ALIASES = {
    "uk_property_search": "property_search", "uk_property_locations": "property_locations",
    "uk_property_dedupe": "property_dedupe", "uk_property_filter": "property_filter", "uk_property_compare": "property_compare",
}


def tool_descriptions() -> List[JsonDict]:
    return [{"name": name, "description": spec["description"], "inputSchema": spec["inputSchema"]} for name, spec in TOOLS.items()]


def _success(request_id: Any, result: JsonDict) -> JsonDict:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: Any, code: int, message: str) -> JsonDict:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def handle_request(request: JsonDict) -> Optional[JsonDict]:
    method, request_id, params = request.get("method"), request.get("id"), request.get("params") or {}
    if method == "initialize":
        return _success(request_id, {"protocolVersion": params.get("protocolVersion", "2024-11-05"), "capabilities": {"tools": {}}, "serverInfo": {"name": "open-properties", "version": __version__}})
    if method == "notifications/initialized": return None
    if method == "tools/list": return _success(request_id, {"tools": tool_descriptions()})
    if method == "tools/call":
        name = ALIASES.get(params.get("name"), params.get("name")); arguments = params.get("arguments") or {}
        if name not in TOOLS: return _error(request_id, -32602, f"Unknown tool: {name}")
        try:
            result = TOOLS[name]["handler"](arguments)
            return _success(request_id, {"content": [{"type": "text", "text": json.dumps(result, indent=2)}], "isError": False})
        except Exception as exc:
            return _success(request_id, {"content": [{"type": "text", "text": str(exc)}], "isError": True})
    return _error(request_id, -32601, f"Method not found: {method}")


def main() -> None:
    for line in sys.stdin:
        if not line.strip(): continue
        try: response = handle_request(json.loads(line))
        except Exception as exc: response = _error(None, -32700, f"Parse error: {exc}")
        if response is not None: print(json.dumps(response), flush=True)


if __name__ == "__main__": main()

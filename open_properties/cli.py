"""Command-line interface for open-properties."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List, Optional

from . import __version__
from .compare import compare_snapshots
from .config import load_profile
from .dedupe import deduplicate_with_report
from .filters import filter_properties_with_reasons
from .io import dump_result, load_properties, write_json
from .locations import find as find_locations
from .portals.base import SearchConfig
from .providers import ADAPTERS, PROVIDERS, list_providers, provider_ids_for, validate_provider
from .schema import utc_now_iso
from .scoring import rank_properties

COUNTRY_DEFAULT_LOCATIONS = {"GB": "edinburgh", "IE": "dublin", "AU": "sydney", "ES": "madrid", "IT": "rome", "PT": "lisbon"}


def _int_or_none(value: Any) -> Optional[int]:
    if value in (None, "", "none", "null"):
        return None
    return int(value)


def build_search_config(args: argparse.Namespace, profile: Dict[str, Any]) -> SearchConfig:
    search = profile.get("search", {})
    country = (args.country or search.get("country") or "GB").upper()
    profile_location = search.get("location") if args.profile else None
    return SearchConfig(
        country=country,
        transaction=args.transaction or search.get("transaction") or "sale",
        min_beds=int(args.min_beds if args.min_beds is not None else (search.get("min_beds") or 1)),
        max_beds=_int_or_none(args.max_beds if args.max_beds is not None else search.get("max_beds")),
        min_baths=_int_or_none(args.min_baths if args.min_baths is not None else search.get("min_baths")),
        max_baths=_int_or_none(args.max_baths if args.max_baths is not None else search.get("max_baths")),
        min_price=str(args.min_price if args.min_price is not None else (search.get("min_price") or "")),
        max_price=str(args.max_price if args.max_price is not None else (search.get("max_price") or "")),
        property_types=args.property_types or ",".join(search.get("property_types") or []),
        location=args.location or profile_location or COUNTRY_DEFAULT_LOCATIONS.get(country, ""),
        location_id=args.location_id or "",
        max_pages=int(args.max_pages or search.get("max_pages") or 3),
        extra={"distance_m": args.distance, "state": args.state, "surrounding": args.surrounding},
    )


def selected_providers(args: argparse.Namespace, config: SearchConfig) -> List[str]:
    requested = args.provider or getattr(args, "portal", None) or "all"
    providers = provider_ids_for(config.country, config.transaction) if requested == "all" else [requested]
    if not providers:
        raise ValueError(f"No providers support {config.transaction} listings in {config.country}")
    for provider in providers:
        validate_provider(provider, config.country, config.transaction)
    return providers


def command_search(args: argparse.Namespace) -> None:
    profile = load_profile(args.profile) if args.profile else load_profile("")
    config = build_search_config(args, profile)
    providers = selected_providers(args, config)

    all_properties: List[Dict[str, Any]] = []
    provider_results = []
    for provider in providers:
        try:
            result = ADAPTERS[provider]().search(config)
        except Exception as exc:  # One provider must not sink an aggregate search.
            result = {"portal": provider, "provider": provider, "country": config.country, "count": 0, "properties": [], "error": str(exc)}
        provider_results.append({key: value for key, value in result.items() if key != "properties"})
        all_properties.extend(result.get("properties", []))

    query = {key: value for key, value in vars(args).items() if key != "func"}
    result: Dict[str, Any] = {
        "tool": "open-properties", "version": __version__, "fetched_at": utc_now_iso(),
        "query": query,
        "resolved_search": {"country": config.country, "transaction": config.transaction, "location": config.location, "providers": providers},
        "provider_results": provider_results, "portal_results": provider_results,
        "count": len(all_properties), "properties": all_properties,
    }

    if args.dedupe or profile.get("deduplication", {}).get("enabled"):
        dconf = profile.get("deduplication", {})
        deduped = deduplicate_with_report(
            result["properties"], threshold=float(args.dedupe_threshold or dconf.get("threshold", 0.88)),
            candidate_threshold=float(dconf.get("candidate_threshold", 0.72)),
        )
        result.update(deduped)
        result["count"] = len(result["properties"])

    criteria = {
        "areas": args.areas.split(",") if args.areas else profile.get("areas", {}).get("desired") or None,
        "exclude": args.exclude.split(",") if args.exclude else profile.get("areas", {}).get("excluded") or None,
        "min_price": _int_or_none(args.min_price), "max_price": _int_or_none(args.max_price),
        "min_beds": _int_or_none(args.min_beds), "max_beds": _int_or_none(args.max_beds), "category": args.category,
    }
    if args.apply_filters:
        kept, removed = filter_properties_with_reasons(result["properties"], **criteria)
        result["filtering"] = {"original_count": len(result["properties"]), "filtered_count": len(kept), "removed_count": len(removed), "criteria": criteria}
        if args.explain:
            result["removed_properties"] = removed
        result["properties"] = kept
        result["count"] = len(kept)

    if args.rank:
        result["properties"] = rank_properties(result["properties"], profile)
    if args.output:
        write_json(args.output, result)
    dump_result(result, jsonl=args.jsonl)


def command_providers(args: argparse.Namespace) -> None:
    rows = list_providers(args.country or "")
    print(json.dumps({"count": len(rows), "providers": rows}, indent=2))


def command_dedupe(args: argparse.Namespace) -> None:
    props = []
    for path in args.files:
        props.extend(load_properties(path))
    dump_result(deduplicate_with_report(props, threshold=args.threshold, candidate_threshold=args.candidate_threshold), jsonl=args.jsonl)


def command_filter(args: argparse.Namespace) -> None:
    props = load_properties(args.input_file)
    kept, removed = filter_properties_with_reasons(
        props, areas=args.areas.split(",") if args.areas else None, exclude=args.exclude.split(",") if args.exclude else None,
        min_price=args.min_price, max_price=args.max_price, min_beds=args.min_beds, max_beds=args.max_beds, category=args.category,
    )
    result: Dict[str, Any] = {"filtering": {"original_count": len(props), "filtered_count": len(kept), "removed_count": len(removed)}, "properties": kept}
    if args.explain:
        result["removed_properties"] = removed
    dump_result(result, jsonl=args.jsonl)


def command_compare(args: argparse.Namespace) -> None:
    dump_result(compare_snapshots(load_properties(args.old), load_properties(args.new)))


def command_locations(args: argparse.Namespace) -> None:
    rows = find_locations(args.query or "", args.country or "")
    print(json.dumps({"locations": rows}, indent=2))


def command_health(args: argparse.Namespace) -> None:
    country = (args.country or "GB").upper()
    statuses = []
    for name in provider_ids_for(country, args.transaction):
        try:
            config = SearchConfig(country=country, transaction=args.transaction, min_beds=1, max_pages=1, location=args.location or COUNTRY_DEFAULT_LOCATIONS.get(country, ""))
            result = ADAPTERS[name]().search(config)
            statuses.append({"provider": name, "ok": "error" not in result, "count": result.get("count", 0), "error": result.get("error", "")})
        except Exception as exc:
            statuses.append({"provider": name, "ok": False, "error": str(exc)})
    print(json.dumps({"country": country, "health": statuses}, indent=2))


def add_search_arguments(search: argparse.ArgumentParser) -> None:
    search.add_argument("--provider", choices=["all", *PROVIDERS], default=None)
    search.add_argument("--portal", choices=["all", *PROVIDERS], help=argparse.SUPPRESS)
    search.add_argument("--country", default=None, help="ISO country code, e.g. GB, IE, AU, ES")
    search.add_argument("--transaction", choices=["sale", "rent"], default=None)
    search.add_argument("--profile", help="Profile name/path from profiles/*.json")
    search.add_argument("--location", default=None, help="City, area or suburb")
    search.add_argument("--location-id", help="Provider location id or Idealista latitude,longitude")
    search.add_argument("--state", help="State code for Domain, e.g. NSW")
    search.add_argument("--distance", type=int, default=20000, help="Idealista radius in metres")
    search.add_argument("--surrounding", action="store_true", help="Include surrounding Domain suburbs")
    search.add_argument("--min-beds", type=int)
    search.add_argument("--max-beds", type=int)
    search.add_argument("--min-baths", type=int)
    search.add_argument("--max-baths", type=int)
    search.add_argument("--min-price", type=int)
    search.add_argument("--max-price", type=int)
    search.add_argument("--property-types", default="")
    search.add_argument("--max-pages", type=int, default=3)
    search.add_argument("--category", choices=["investment", "family", "other"])
    search.add_argument("--areas", help="Comma-separated desired areas/postcodes")
    search.add_argument("--exclude", help="Comma-separated excluded areas/postcodes")
    search.add_argument("--apply-filters", action="store_true")
    search.add_argument("--explain", action="store_true")
    search.add_argument("--dedupe", action="store_true")
    search.add_argument("--dedupe-threshold", type=float)
    search.add_argument("--rank", action="store_true")
    search.add_argument("--jsonl", action="store_true")
    search.add_argument("--output")


def build_parser(prog: str = "property") -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=prog, description="Search property portals around the world with normalized JSON output")
    parser.add_argument("--version", action="version", version=f"open-properties {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    providers = sub.add_parser("providers", help="List providers, countries, auth and capabilities")
    providers.add_argument("--country")
    providers.set_defaults(func=command_providers)

    search = sub.add_parser("search", help="Search one provider or every provider for a country")
    add_search_arguments(search)
    search.set_defaults(func=command_search)

    dedupe = sub.add_parser("dedupe", help="Deduplicate one or more JSON files")
    dedupe.add_argument("files", nargs="+")
    dedupe.add_argument("--threshold", type=float, default=0.88)
    dedupe.add_argument("--candidate-threshold", type=float, default=0.72)
    dedupe.add_argument("--jsonl", action="store_true")
    dedupe.set_defaults(func=command_dedupe)

    filt = sub.add_parser("filter", help="Filter a JSON property file")
    filt.add_argument("input_file")
    filt.add_argument("--areas"); filt.add_argument("--exclude")
    filt.add_argument("--min-price", type=int); filt.add_argument("--max-price", type=int)
    filt.add_argument("--min-beds", type=int); filt.add_argument("--max-beds", type=int)
    filt.add_argument("--category", choices=["investment", "family", "other"])
    filt.add_argument("--explain", action="store_true"); filt.add_argument("--jsonl", action="store_true")
    filt.set_defaults(func=command_filter)

    comp = sub.add_parser("compare", help="Compare two snapshots")
    comp.add_argument("old"); comp.add_argument("new"); comp.set_defaults(func=command_compare)

    loc = sub.add_parser("locations", help="Find known provider location identifiers")
    loc.add_argument("query", nargs="?", default=""); loc.add_argument("--country"); loc.set_defaults(func=command_locations)

    health = sub.add_parser("health", help="Smoke-test providers for one country")
    health.add_argument("--country", default="GB"); health.add_argument("--transaction", choices=["sale", "rent"], default="sale")
    health.add_argument("--location", default=None); health.set_defaults(func=command_health)
    return parser


def main(argv: Optional[List[str]] = None, prog: str = "property") -> None:
    args = build_parser(prog).parse_args(argv)
    try:
        args.func(args)
    except (ValueError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()

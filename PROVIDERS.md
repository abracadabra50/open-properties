# Provider contract and coverage

`open_properties/providers.py` is the machine-readable registry. This document explains the adapter contract and why the initial international set looks the way it does.

## Adapter contract

Every adapter receives `SearchConfig` and returns:

```json
{
  "provider": "provider-id",
  "portal": "provider-id",
  "country": "IE",
  "fetched_at": "ISO-8601",
  "count": 2,
  "fetch_urls": ["https://..."],
  "properties": []
}
```

A partial or unavailable provider returns the same object with an `error` string. Aggregate search can then retain successful sources and make the missing coverage explicit.

Every listing must pass through `normalise_listing` and include:

- stable provider `id` and canonical `url`;
- `portal`, ISO `country`, ISO `currency`, `transaction`;
- numeric whole-unit `price` plus the provider's `price_text`;
- address, beds, baths and property type when available;
- `fetched_at`, `parser_version` and `fetch_url` provenance.

Do not copy provider-specific payloads wholesale into `source`. Keep only compact provenance that helps debug or verify a listing.

## Current providers

### Rightmove — GB

The storefront embeds search results as JSON. No credentials. Sale and rent use parallel URL shapes. Live exercised during the 1.0 rebuild.

### ESPC — GB

Regional Edinburgh/Lothians HTML source. No credentials. Sale only. Its value is local inventory that can be deduplicated against nationwide portals.

### Zoopla — GB

The public storefront is Cloudflare-protected from direct server requests. The adapter uses an optional Firecrawl CLI rather than pretending a bare HTTP parser is reliable.

### Daft.ie — IE

The storefront posts JSON to `gateway.daft.ie/api/v2/ads/listings` with public web-client headers. No account or key. Supports sale and rent, paging, location IDs, bed/bath and price ranges. Live exercised during the 1.0 rebuild.

### Domain — AU

Official OAuth2 client-credentials API. Search requires `DOMAIN_CLIENT_ID` and `DOMAIN_CLIENT_SECRET` with `api_listings_read`. The adapter uses `POST /v1/listings/residential/_search` and maps `PropertyListing` results. Project groups are deliberately skipped until their child-listing behavior is fixture-tested.

### Idealista — ES, IT, PT

Official OAuth2 API. Requires `IDEALISTA_API_KEY` and `IDEALISTA_API_SECRET`. Search is radius-based, so the adapter resolves common cities to coordinates and accepts arbitrary `--location-id latitude,longitude` values.

## Evaluated but not shipped

These are not TODO checkboxes pretending to be integrations. They record what a contributor must solve.

| Market/source | Finding |
|---|---|
| Redfin — US | Internal Stingray API is useful but currently AWS WAF-blocked from plain CLI HTTP. A browser-session transport would be an optional adapter, not a zero-credential core provider. |
| REALTOR.ca — CA | `PropertySearch_Post` is behind an Imperva browser challenge. Bare HTTP returns challenge HTML; a browser-warmed session is required. |
| Daft old endpoint — IE | `/old/v1/listings` is obsolete. The working storefront endpoint is `/api/v2/ads/listings` with `brand: daft` and `platform: web`. |
| Zillow/Realtor.com — US | No stable public consumer listing API has been verified for a dependency-free adapter. Do not add an unverified RapidAPI proxy and call it native support. |
| Funda — NL | Not yet investigated deeply enough to claim a reliable access path. |
| ImmoScout24 — DE | Has an official developer API and is the strongest next credentialed provider; access, scopes and a fixture-backed response mapper still need verification. |

## Adding a provider

1. Verify access from a clean environment.
2. Implement `PortalAdapter.search` under `open_properties/portals/`.
3. Add exact countries, transactions, auth and access notes to the registry.
4. Add a compact synthetic or redacted fixture test for URL, price, currency, location and image mapping.
5. Run the live health check if access permits it.
6. Update the README table only after the registry and tests agree.

A provider that needs credentials is valid. A provider that needs a browser transport is valid. The requirement is honesty: declare the transport and failure mode instead of returning an unexplained empty list.

import json
import unittest
from unittest.mock import patch

from open_properties.cli import build_parser
from open_properties.dedupe import match_confidence, merge_property_data
from open_properties.locations import resolve
from open_properties.portals.base import SearchConfig
from open_properties.portals.daft import DaftAdapter
from open_properties.portals.domain import DomainAdapter
from open_properties.portals.idealista import IdealistaAdapter
from open_properties.providers import list_providers, provider_ids_for


class InternationalProviderTests(unittest.TestCase):
    def test_registry_is_country_and_transaction_aware(self):
        self.assertEqual(provider_ids_for("IE", "sale"), ["daft"])
        self.assertEqual(provider_ids_for("AU", "rent"), ["domain"])
        self.assertIn("idealista", provider_ids_for("ES", "sale"))
        self.assertEqual({row["id"] for row in list_providers("GB")}, {"rightmove", "espc", "zoopla"})

    def test_location_resolver_supports_international_ids(self):
        self.assertEqual(resolve("daft", "dublin-city"), "33")
        self.assertEqual(resolve("idealista", "madrid"), "40.4168,-3.7038")

    def test_daft_payload_and_normalisation(self):
        adapter = DaftAdapter()
        config = SearchConfig(country="IE", transaction="sale", location="dublin-city", min_beds=2, max_price="600000")
        payload = adapter.build_payload(config)
        self.assertEqual(payload["geoFilter"]["storedShapeIds"], ["33"])
        self.assertIn({"name": "salePrice", "from": "0", "to": "600000"}, payload["ranges"])

        listing = adapter.parse_listing({"listing": {
            "id": 123, "title": "1 Test Street, Dublin 2, D02AB12", "seoFriendlyPath": "/for-sale/test/123",
            "price": "€550,000", "numBedrooms": "2 Bed", "numBathrooms": "1 Bath", "propertyType": "Apartment",
            "point": {"coordinates": [-6.25, 53.34]}, "media": {"images": [{"size720x480": "https://img.example/1.jpg"}]},
            "sections": ["Property", "Apartment"],
        }}, adapter.endpoint, "sale")
        self.assertEqual(listing["country"], "IE")
        self.assertEqual(listing["currency"], "EUR")
        self.assertEqual(listing["price"], 550000)
        self.assertEqual(listing["postcode"], "D02AB12")
        self.assertEqual(listing["latitude"], 53.34)

    def test_domain_mapping(self):
        listing = DomainAdapter().parse_listing({"type": "PropertyListing", "listing": {
            "id": 9, "listingType": "Sale", "listingSlug": "1-test-street-sydney-nsw-2000-9",
            "headline": "City apartment", "priceDetails": {"displayPrice": "$900,000", "price": 900000},
            "propertyDetails": {"displayableAddress": "1 Test Street, Sydney", "state": "NSW", "suburb": "Sydney", "postcode": "2000", "bedrooms": 2, "bathrooms": 1, "propertyType": "Apartment", "latitude": -33.8, "longitude": 151.2},
            "media": [{"category": "Image", "url": "https://img.example/au.jpg"}],
        }})
        self.assertEqual(listing["country"], "AU")
        self.assertEqual(listing["currency"], "AUD")
        self.assertEqual(listing["price"], 900000)

    def test_idealista_mapping(self):
        listing = IdealistaAdapter().parse_listing({
            "propertyCode": "x", "url": "https://idealista.example/x", "address": "Calle Test, Madrid",
            "price": 450000, "rooms": 2, "bathrooms": 1, "propertyType": "flat", "municipality": "Madrid",
            "size": 70, "latitude": 40.4, "longitude": -3.7,
        }, "ES", "sale")
        self.assertEqual(listing["country"], "ES")
        self.assertEqual(listing["floor_area_sqm"], 70.0)

    def test_dedupe_never_merges_countries_or_currencies(self):
        a = {"portal": "a", "id": "1", "address": "1 High Street", "country": "GB", "currency": "GBP", "price": 100, "beds": 1}
        b = {"portal": "b", "id": "2", "address": "1 High Street", "country": "IE", "currency": "EUR", "price": 100, "beds": 1}
        score, reasons = match_confidence(a, b)
        self.assertEqual(score, 0)
        self.assertIn("different countries", reasons)

    def test_merge_formats_source_currency(self):
        merged = merge_property_data([
            {"portal": "a", "id": "1", "url": "a", "address": "x", "country": "IE", "currency": "EUR", "price": 100, "images": [], "features": []},
            {"portal": "b", "id": "2", "url": "b", "address": "x", "country": "IE", "currency": "EUR", "price": 90, "images": [], "features": []},
        ])
        self.assertEqual(merged["price_text"], "€90")

    def test_cli_brand_and_compatibility_alias(self):
        parser = build_parser()
        args = parser.parse_args(["search", "--provider", "daft", "--country", "IE", "--location", "dublin"])
        self.assertEqual(args.provider, "daft")
        self.assertEqual(args.country, "IE")


if __name__ == "__main__":
    unittest.main()

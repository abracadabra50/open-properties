#!/usr/bin/env python3
import unittest

from dedupe import (
    addresses_match, deduplicate, merge_property_data, normalize_address, properties_match,
)


class NormalizeAddressTests(unittest.TestCase):
    def test_normalizes_case_punctuation_suffixes_and_whitespace(self):
        self.assertEqual(
            normalize_address("  12, MAIN. STREET   	Edinburgh  "),
            "12 main st edinburgh",
        )

    def test_empty_and_none_addresses_normalize_to_empty_string(self):
        for address in ("", "   ", None):
            with self.subTest(address=address):
                self.assertEqual(normalize_address(address), "")

    def test_non_string_address_raises_attribute_error(self):
        with self.assertRaises(AttributeError):
            normalize_address(123)


class DedupeRegressionTests(unittest.TestCase):
    def test_same_portal_different_ids_do_not_merge_even_with_same_address(self):
        a = {
            "portal": "rightmove",
            "id": "174727811",
            "url": "https://www.rightmove.co.uk/properties/174727811",
            "address": "High Street, Cowdenbeath, Fife, KY4",
            "price": 105000,
            "beds": 1,
            "baths": 1,
            "images": ["https://media.rightmove.co.uk/property-photo/x/174727811/a.jpeg"],
        }
        b = {
            "portal": "rightmove",
            "id": "174728315",
            "url": "https://www.rightmove.co.uk/properties/174728315",
            "address": "High Street, Cowdenbeath, Fife, KY4",
            "price": 120000,
            "beds": 1,
            "baths": 1,
            "images": ["https://media.rightmove.co.uk/property-photo/x/174728315/b.jpeg"],
        }

        self.assertFalse(properties_match(a, b))
        self.assertEqual(len(deduplicate([a, b])), 2)

    def test_same_portal_same_id_merges(self):
        a = {"portal": "rightmove", "id": "1", "url": "u1", "address": "High Street, KY4", "price": 100, "beds": 1, "baths": 1}
        b = {"portal": "rightmove", "id": "1", "url": "u1", "address": "High Street, KY4", "price": 95, "beds": 1, "baths": 1}

        self.assertTrue(properties_match(a, b))
        self.assertEqual(len(deduplicate([a, b])), 1)

    def test_distinct_streets_in_same_town_do_not_merge(self):
        self.assertFalse(addresses_match(
            "Salisbury Street, Kirkcaldy, Fife, KY2",
            "Balfour Street, KIRKCALDY, Fife, KY2",
        ))

    def test_cross_portal_address_variants_still_merge(self):
        self.assertTrue(addresses_match(
            "14 11 High Riggs Edinburgh, EH3 9Bx",
            "High Riggs, Edinburgh EH3",
        ))

    def test_merge_preserves_image_order_and_structured_features(self):
        merged = merge_property_data([
            {
                "portal": "espc", "id": "a", "url": "u1", "address": "High Riggs", "price": 10, "beds": 1, "baths": 1,
                "images": ["img1", "img2"], "features": [{"label": "Home Report"}], "description": "short",
            },
            {
                "portal": "rightmove", "id": "b", "url": "u2", "address": "High Riggs", "price": 9, "beds": 1, "baths": 1,
                "images": ["img2", "img3"], "features": [{"label": "Home Report"}, "Garden"], "description": "a longer description",
            },
        ])

        self.assertEqual(merged["images"], ["img1", "img2", "img3"])
        self.assertEqual(merged["price"], 9)
        self.assertEqual(merged["features"], [{"label": "Home Report"}, "Garden"])
        self.assertEqual(merged["description"], "a longer description")


if __name__ == "__main__":
    unittest.main()

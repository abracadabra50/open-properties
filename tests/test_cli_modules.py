import json
import unittest
from pathlib import Path

from open_properties.compare import compare_snapshots
from tempfile import TemporaryDirectory

from open_properties.config import load_profile
from open_properties.dedupe import deduplicate_with_report, match_confidence
from open_properties.filters import filter_properties_with_reasons
from open_properties.locations import find, resolve
from open_properties.portals.base import SearchConfig
from open_properties.portals.rightmove import RightmoveAdapter
from open_properties.schema import normalise_listing


class PackageBehaviourTests(unittest.TestCase):
    def test_schema_normalises_price_and_required_fields(self):
        prop = normalise_listing({"id": 1, "portal": "Rightmove", "url": "u", "address": "  A   B  ", "price": "£200,000", "beds": "1"})
        self.assertEqual(prop["portal"], "rightmove")
        self.assertEqual(prop["price"], 200000)
        self.assertEqual(prop["address"], "A B")
        self.assertEqual(prop["schema_version"], "property-listing.v1")

    def test_location_resolver_hides_rightmove_magic(self):
        self.assertEqual(resolve("rightmove", "edinburgh"), "REGION^475")
        self.assertTrue(any(row["value"] == "REGION^475" for row in find("edinburgh")))

    def test_rightmove_fixture_parse(self):
        html = Path("tests/fixtures/rightmove_sample.html").read_text()
        adapter = RightmoveAdapter()
        raw, count = adapter.extract_props_from_html(html)
        self.assertEqual(count, 1)
        prop = adapter.parse_property(raw[0], "https://fetch.example", "REGION^475")
        self.assertEqual(prop["portal"], "rightmove")
        self.assertEqual(prop["price"], 200000)
        self.assertEqual(prop["postcode"], "EH3 9AA")
        self.assertEqual(prop["parser_version"], "rightmove-nextjs-v2")


    def test_espc_fixture_parse(self):
        from open_properties.portals.espc import ESPCAdapter
        html = Path("tests/fixtures/espc_sample.html").read_text()
        adapter = ESPCAdapter()
        props = adapter.parse_properties(html, SearchConfig(min_beds=1), "https://fetch.example")
        self.assertEqual(len(props), 1)
        self.assertEqual(props[0]["portal"], "espc")
        self.assertEqual(props[0]["price"], 210000)

    def test_zoopla_fixture_parse(self):
        from open_properties.portals.zoopla import ZooplaAdapter
        md = Path("tests/fixtures/zoopla_sample.md").read_text()
        adapter = ZooplaAdapter()
        props = adapter.parse_properties(md, "https://fetch.example")
        self.assertEqual(len(props), 1)
        self.assertEqual(props[0]["portal"], "zoopla")
        self.assertEqual(props[0]["price"], 220000)

    def test_dedupe_reports_candidates_and_avoids_same_portal_frankenflat(self):
        a = {"portal": "rightmove", "id": "1", "url": "u1", "address": "High Street, Edinburgh, EH3", "price": 100000, "beds": 1, "baths": 1}
        b = {"portal": "rightmove", "id": "2", "url": "u2", "address": "High Street, Edinburgh, EH3", "price": 100000, "beds": 1, "baths": 1}
        c = {"portal": "espc", "id": "3", "url": "u3", "address": "High St, Edinburgh EH3", "price": 101000, "beds": 1, "baths": 1}
        report = deduplicate_with_report([a, b, c], threshold=0.82, candidate_threshold=0.5)
        self.assertEqual(report["deduplication"]["unique_count"], 2)
        self.assertTrue(any(cand["merged"] for cand in report["duplicate_candidates"]))

    def test_filter_explains_removals(self):
        props = [
            {"address": "Good Street, EH3", "postcode": "EH3", "price": 200000, "beds": 1},
            {"address": "Bad Street, EH17", "postcode": "EH17", "price": 300000, "beds": 1},
        ]
        kept, removed = filter_properties_with_reasons(props, areas=["EH3"], exclude=["EH17"], max_price=250000)
        self.assertEqual(len(kept), 1)
        self.assertGreaterEqual(len(removed[0]["filter_reasons"]), 1)

    def test_compare_uses_portal_id_key(self):
        old = [{"portal": "rightmove", "id": "1", "price": 100000}]
        new = [{"portal": "rightmove", "id": "1", "price": 90000}]
        result = compare_snapshots(old, new)
        self.assertEqual(result["stats"]["price_drops"], 1)

    def test_profile_loads_from_explicit_external_path(self):
        with TemporaryDirectory() as tmp:
            profile_path = Path(tmp) / "agent-profile.json"
            profile_path.write_text(json.dumps({"name": "agent-profile", "deduplication": {"enabled": True}}))
            profile = load_profile(str(profile_path))
        self.assertEqual(profile["name"], "agent-profile")
        self.assertTrue(profile["deduplication"]["enabled"])


if __name__ == "__main__":
    unittest.main()

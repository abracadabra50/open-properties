import json
import unittest

from open_properties.mcp_server import handle_request


class MCPServerTests(unittest.TestCase):
    def test_initialize_and_list_tools(self):
        init = handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        self.assertEqual(init["result"]["serverInfo"]["name"], "open-properties")
        self.assertIn("tools", init["result"]["capabilities"])

        listed = handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        names = {tool["name"] for tool in listed["result"]["tools"]}
        self.assertIn("property_search", names)
        self.assertIn("property_dedupe", names)
        self.assertIn("property_compare", names)

    def test_locations_tool_returns_json_text_content(self):
        response = handle_request({
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "property_locations", "arguments": {"query": "edinburgh"}},
        })
        self.assertFalse(response["result"]["isError"])
        payload = json.loads(response["result"]["content"][0]["text"])
        self.assertTrue(any(row["value"] == "REGION^475" for row in payload["locations"]))

    def test_dedupe_tool_avoids_same_portal_frankenflat(self):
        response = handle_request({
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "property_dedupe",
                "arguments": {
                    "properties": [
                        {"portal": "rightmove", "id": "1", "url": "u1", "address": "High Street, EH3", "price": 100000, "beds": 1},
                        {"portal": "rightmove", "id": "2", "url": "u2", "address": "High Street, EH3", "price": 110000, "beds": 1},
                    ]
                },
            },
        })
        payload = json.loads(response["result"]["content"][0]["text"])
        self.assertEqual(payload["deduplication"]["unique_count"], 2)

    def test_unknown_tool_returns_tool_error_not_process_crash(self):
        response = handle_request({
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {"name": "missing", "arguments": {}},
        })
        self.assertIn("error", response)


if __name__ == "__main__":
    unittest.main()

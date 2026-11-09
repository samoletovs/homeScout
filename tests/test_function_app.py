"""Listings HTTP endpoint tests (offline, temporary SQLite store)."""
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import azure.functions as func

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "functions"))

from function_app import app  # noqa: E402
from models import Listing  # noqa: E402
from store import Store, open_store  # noqa: E402


class ListingsEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.functions = {f.get_function_name(): f for f in app.get_functions()}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "listings.sqlite")
        self.req = func.HttpRequest(method="GET", url="http://localhost/api/listings", body=b"")

    def invoke(self):
        with patch("function_app.open_store", side_effect=lambda: open_store(self.path)):
            return self.functions["get_listings"].get_user_function()(self.req)

    def test_empty_store_returns_json_array(self):
        response = self.invoke()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/json")
        self.assertEqual(json.loads(response.get_body()), [])

    def test_returns_persisted_listings(self):
        store = Store(self.path)
        try:
            store.filter_new([
                Listing(id="1", source="city24", url="https://city24.lv/1",
                        price=190000, area_m2=78, rooms=3, district="Mārupe"),
                Listing(id="2", source="ss.lv", url="https://ss.lv/2"),
            ])
            expected = store.get_listings()
        finally:
            store.close()

        response = self.invoke()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.get_body()), expected)
        self.assertIn("Mārupe", response.get_body().decode("utf-8"))

    def test_route_is_get_only_and_function_key_protected(self):
        bindings = self.functions["get_listings"].get_dict_repr()["bindings"]
        trigger = next(b for b in bindings if b["type"] == "httpTrigger")
        self.assertEqual(trigger["route"], "listings")
        self.assertEqual(trigger["methods"], [func.HttpMethod.GET])
        self.assertEqual(trigger["authLevel"], func.AuthLevel.FUNCTION)

    def test_store_closed_after_success_or_failure(self):
        for error in (None, RuntimeError("store unavailable")):
            with self.subTest(error=error):
                store = Mock()
                store.get_listings.return_value = []
                store.get_listings.side_effect = error
                with patch("function_app.open_store", return_value=store):
                    handler = self.functions["get_listings"].get_user_function()
                    if error:
                        with self.assertRaises(RuntimeError):
                            handler(self.req)
                    else:
                        handler(self.req)
                store.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()

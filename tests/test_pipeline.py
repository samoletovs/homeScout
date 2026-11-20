import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "functions"))

import pipeline  # noqa: E402
from models import Listing  # noqa: E402
from scoring import HardFilters  # noqa: E402


class FloodFilteringTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_once_excludes_a_listing_marked_flooded_by_enrichment(self):
        listing = Listing(
            id="flooded", source="city24", url="u", lat=56.95, lon=24.11,
        )
        filters = HardFilters(
            min_rooms=None, min_area=None, exclude_rented=False, require_ready=False,
        )
        store = MagicMock()
        store.is_empty.return_value = False
        store.filter_new.return_value = [(listing, "new")]

        async def mark_flooded(listings, *_args, **_kwargs):
            for item in listings:
                item.flood_risk = True

        with patch("pipeline.HardFilters.from_env", return_value=filters), patch(
            "pipeline.open_store", return_value=store
        ), patch("pipeline.fetch_all", new_callable=AsyncMock, return_value=[listing]), patch(
            "pipeline.enrich_all", side_effect=mark_flooded
        ), patch("pipeline.adviser_enabled", return_value=False):
            result = await pipeline.run_once(notify_results=False)

        self.assertEqual(result, [])
        store.save_evaluation.assert_not_called()


if __name__ == "__main__":
    unittest.main()

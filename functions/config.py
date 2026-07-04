"""Configuration — feeds, target areas, env access. No secrets committed."""
from __future__ import annotations

import os

USER_AGENT = "Mozilla/5.0 homeScout/0.1 (+https://github.com/samoletovs/homeScout)"

_SS = "https://www.ss.lv/lv/real-estate"

# ss.lv sale RSS feeds (URL, area label). The '/sell/' segment excludes rentals.
SSLV_FEEDS: list[tuple[str, str]] = [
    (f"{_SS}/flats/riga/sell/rss/", "Rīga"),
    (f"{_SS}/flats/jurmala/sell/rss/", "Jūrmala"),
    (f"{_SS}/flats/riga-region/marupes-pag/marupe/sell/rss/", "Mārupe"),
    (f"{_SS}/homes-summer-residences/riga-region/marupes-pag/marupe/sell/rss/", "Mārupe"),
]

# city24 sale apartments (Latvia-wide); filtered client-side to the target areas.
CITY24_URL = (
    "https://api.city24.ee/lv_LV/search/realties"
    "?tsType=sale&unitType=Apartment&itemsPerPage=100"
)
CITY24_TARGET_AREAS = {"Rīga", "Jūrmala", "Mārupe", "Mārupes novads"}

# Dedup/state DB (git-ignored). Durable on a home machine; ephemeral on Functions
# consumption plan — move to Cosmos DB for durable cloud state (see AGENTS.md).
DB_PATH = os.getenv("HOMESCOUT_DB", "data/homescout.sqlite")

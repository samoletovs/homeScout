"""Configuration — feeds, target areas, env access. No secrets committed."""
from __future__ import annotations

import os

USER_AGENT = "Mozilla/5.0 homeScout/0.1 (+https://github.com/samoletovs/homeScout)"

_SS = "https://www.ss.lv/lv/real-estate"

# ss.lv sale RSS feeds (URL, area label). The '/sell/' segment excludes rentals.
SSLV_FEEDS: list[tuple[str, str, str]] = [
    (f"{_SS}/flats/riga/sell/rss/", "Rīga", "apartment"),
    (f"{_SS}/flats/jurmala/sell/rss/", "Jūrmala", "apartment"),
    (f"{_SS}/flats/riga-region/marupes-pag/marupe/sell/rss/", "Mārupe", "apartment"),
    (f"{_SS}/homes-summer-residences/riga-region/marupes-pag/marupe/sell/rss/", "Mārupe", "house"),
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


# ── Enrichment (Phase 2) ─────────────────────────────────────────────────
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_URLS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
]
ORS_MATRIX_URL = "https://api.openrouteservice.org/v2/matrix/driving-car"
ORS_API_KEY = os.getenv("ORS_API_KEY", "")

SCHOOL_RADIUS_M = int(os.getenv("HOMESCOUT_SCHOOL_RADIUS_M", "2000"))
ENRICH_CAP = int(os.getenv("HOMESCOUT_ENRICH_CAP", "15"))


def _commute_dest() -> tuple[float, float]:
    """Commute target 'lat,lon' (default: central Rīga). No personal data in the repo."""
    raw = os.getenv("HOMESCOUT_COMMUTE_DEST", "56.9489,24.1064")
    try:
        lat, lon = (float(x) for x in raw.split(","))
        return lat, lon
    except ValueError:
        return 56.9489, 24.1064


COMMUTE_DEST = _commute_dest()


# ── Adviser (LLM take) ────────────────────────────────────────────────
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY", "")
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21")
ADVISE_TOP_N = int(os.getenv("HOMESCOUT_ADVISE_TOP", "5"))

# Concise buyer context for the adviser (no budget, no names). Override with HOMESCOUT_PROFILE.
FAMILY_PROFILE = os.getenv(
    "HOMESCOUT_PROFILE",
    "Family of 2 adults + 2 kids (~9 and 11) buying a turnkey home: >=4 rooms plus a "
    "work-from-home office, parking, outdoor space, not ground floor. Areas by priority: "
    "Mārupe (near Mārupes ģimnāzija + airport, ~7 km to centre), then central Rīga "
    "(riverside/Daugava a plus), then Jūrmala (seaside a plus). Values: easy city + airport "
    "access (a parent travels for work; a child plays football in Rīga), school proximity, "
    "space, near water, fair price vs the area, newer/efficient. Watching steadily 6-12 months.",
)

# Family communication language (stored data stays English). ru = Russian.
COMM_LANGUAGE = os.getenv("HOMESCOUT_LANG", "ru")

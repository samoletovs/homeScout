# homeScout — Agent Instructions

> Project-specific instructions for AI coding agents (Copilot, Codex, Claude Code).

## Project

Property-intelligence pipeline for a family buying a home in Mārupe / Rīga / Jūrmala.
Ingests new listings, values them against real sold-deal data, watches auctions, enriches,
scores, and alerts a ranked shortlist. Python Azure Functions (v2) + Cosmos + Telegram,
with an optional SWA dashboard. Grew out of agentMode's `property_search` skill.

## Build / test / verify

```bash
cd functions
pip install -r requirements.txt
python -m unittest discover ../tests    # MUST pass (parser/scorer/store are stdlib-only)
python ../scripts/run_once.py           # LIVE fetch: ss.lv + city24 → prints alertable listings
```

## Project structure

```
functions/
├── function_app.py   # Azure Functions entry (timer trigger → pipeline.run_once)
├── pipeline.py       # ingest → dedupe → store(seen) → enrich → notify
├── sources.py        # async fetchers: ss.lv RSS + city24 (curl_cffi); izsoles/NĪTIS stubs
├── parsers.py        # pure payload → Listing parsers (unit-tested)
├── enrich.py         # geocode (Nominatim) + nearest school/kindergarten (local OSM) + commute (ORS)
├── geo.py            # pure geo helpers: haversine, parsing, proximity score
├── store.py          # SQLite dedup / seen-state + price history + geocode cache
├── notify.py         # Telegram sender + message formatting
├── config.py         # feeds, target areas, enrichment endpoints, env
├── scoring.py        # hard filters + deterministic weighted-sum (used from Phase 4)
├── models.py         # Listing / Deal / ScoredListing (dataclasses, stdlib)
├── assets/lv_amenities.json   # committed OSM schools+kindergartens (ODbL)
├── host.json
└── requirements.txt
infrastructure/main.bicep    # monitoring module + (TODO) Functions + Cosmos
tests/                       # parsers/store/notify/scoring/geo/enrich (30 tests)
scripts/run_once.py          # local one-shot runner (live fetch)
scripts/refresh_amenities.py # refresh the committed OSM amenities dataset
```

## Data sources (verified endpoints)

| Source | Access | Notes |
|--------|--------|-------|
| ss.lv | RSS `…/real-estate/flats/{city}/rss/` (ttl=5) | volume leader; robots allows `/rss/` |
| city24.lv | JSON `https://api.city24.ee/lv_LV/search/realties?tsType=sale&unitType=Apartment` | richest — has lat/long + energy class |
| VZD NĪTIS (sold deals) | data.gov.lv CKAN `package_show?id=nekustama-ipasuma-tirgus-datu-bazes-atvertie-dati` | CC BY 4.0, monthly; the valuation layer |
| izsoles.ta.gov.lv | no API → scrape filtered HTML | court e-auctions; heavy buyer risk (see §Auction) |
| Enrichment | OpenRouteService (commute); OSM schools/kindergartens (committed dataset, refresh script); flood: TODO | free tiers |

## Key conventions

- Python 3.11, async where it helps (network fan-out).
- Use `logging`, never `print()` (except `scripts/run_once.py`).
- **Scoring is deterministic** — the LLM only *extracts* features/booleans from listing
  text/photos (structured outputs); the weighted-sum is computed in code. LLMs are
  unreliable at direct numeric ranking. Keep it that way.
- **Prefer structured feeds over HTML scraping** (RSS, the city24 JSON API). HTML scrape
  is the fallback. Alert on zero-results/parse-failure — don't fail silently.
- **Some Latvian/OSM endpoints TLS-fingerprint clients** — city24's JSON API gets 403 and
  the main Overpass instance 406s over plain httpx. Use `curl_cffi` (`impersonate="chrome"`)
  for those. ss.lv RSS, Nominatim geocoding, and ORS are fine over httpx. School/kindergarten
  data is fetched once into `functions/assets/lv_amenities.json` (refresh script) to avoid a
  runtime Overpass dependency.
- **Ingest from a residential IP** where portals block datacenter IPs; keep request rates
  low and respectful (personal, non-republishing use only).
- Secrets: `functions/local.settings.json` locally, SWA App Settings / Function App
  settings in cloud. Never commit secrets or personal figures.

## Auction path (izsoles) — treat as opportunistic Plan B

Monitor real-estate auctions but flag only ones that pass a strict due-diligence
checklist: clear **title**, no inherited **debts** (since June 2025 buyers inherit the
flat's prior utility/reserve-fund debts), **occupancy** status (eviction via *ievešana
valdījumā* is slow), interior **inspection** where possible, and **cash-ready** (winner
pays in full within ~1 month; a standard mortgage timeline doesn't fit).

## Off-path deviation (vs PLATFORM.md)

The lab default is React + SWA Free with SWA-managed Functions. homeScout deviates: it is a
**Python Azure Functions** timer-driven pipeline + **Cosmos DB** (state/price-history/dedup)
+ Telegram, with SWA used only for a later read-only dashboard. Rationale: it's a
backend data pipeline (like agentMode/mindMe), not a frontend app. Follow agentMode's
Functions patterns.

## Build plan (phases)

1. ✅ **MVP (built)** — ss.lv RSS + city24 JSON → dedupe/store → Telegram alerts.
2. ✅ **Enrichment (built)** — geocode + nearest school/kindergarten + commute (ORS) + €/m².
3. Valuation — €/m² vs NĪTIS comparables → over/under-priced.
4. Scoring — hard filters + weighted-sum → ranked shortlist.
5. Auction watch — izsoles scrape + due-diligence checklist.
6. Dashboard + price history (SWA).

## Known limitations

- **State durability:** the SQLite store persists on a home machine (the recommended
  residential-IP host) but is ephemeral on the Functions consumption plan — move dedup
  state to Cosmos DB for durable cloud runs (Phase 6 / infra).
- **city24 requires `curl_cffi`** (browser TLS impersonation); it degrades gracefully to
  ss.lv-only if that dep is missing or city24 rate-limits.
- **Commute needs an `ORS_API_KEY`** (OpenRouteService free tier); without it, commute is
  left unset (alerts still send).
- **Schools/kindergartens** use a committed OSM snapshot (`functions/assets/lv_amenities.json`,
  greater-Rīga bbox); refresh with `scripts/refresh_amenities.py`. ss.lv listings are
  geocoded at **district level** (Nominatim), so distances are approximate.
- **Flood risk** is not yet wired (Phase 2.1 — ĢEOLatvija WFS point-in-polygon).
- Telegram send is a no-op (logs alerts) until `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`
  are set.

## Hypothesis

_Can an AI-assisted, multi-source pipeline surface fairly-priced, family-suitable homes
faster and with better judgment than manual portal-watching — enough to change which
property gets bought?_

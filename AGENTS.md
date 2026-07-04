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
python -m unittest discover ../tests    # MUST pass (scorer is stdlib-only)
python -c "import scoring, models, pipeline, sources"   # imports must succeed
python ../scripts/run_once.py           # dry-run pipeline on sample data
```

## Project structure

```
functions/
├── function_app.py   # Azure Functions entry (timer trigger → pipeline.run_once)
├── pipeline.py       # ingest → dedupe → enrich → value → extract → score → notify
├── sources.py        # portal adapters (ss.lv RSS, city24 JSON, izsoles, VZD NĪTIS)
├── scoring.py        # hard filters + deterministic weighted-sum (the "brain")
├── models.py         # Listing / Deal / ScoredListing (dataclasses, stdlib)
├── host.json
└── requirements.txt
infrastructure/main.bicep   # monitoring module + (TODO) Functions + Cosmos
tests/test_scoring.py       # scorer unit tests
scripts/run_once.py         # local one-shot runner
```

## Data sources (verified endpoints)

| Source | Access | Notes |
|--------|--------|-------|
| ss.lv | RSS `…/real-estate/flats/{city}/rss/` (ttl=5) | volume leader; robots allows `/rss/` |
| city24.lv | JSON `https://api.city24.ee/lv_LV/search/realties?tsType=sale&unitType=Apartment` | richest — has lat/long + energy class |
| VZD NĪTIS (sold deals) | data.gov.lv CKAN `package_show?id=nekustama-ipasuma-tirgus-datu-bazes-atvertie-dati` | CC BY 4.0, monthly; the valuation layer |
| izsoles.ta.gov.lv | no API → scrape filtered HTML | court e-auctions; heavy buyer risk (see §Auction) |
| Enrichment | OpenRouteService (commute), ĢEOLatvija WFS (schools/flood), OSM Overpass (amenities) | free tiers |

## Key conventions

- Python 3.11, async where it helps (network fan-out).
- Use `logging`, never `print()` (except `scripts/run_once.py`).
- **Scoring is deterministic** — the LLM only *extracts* features/booleans from listing
  text/photos (structured outputs); the weighted-sum is computed in code. LLMs are
  unreliable at direct numeric ranking. Keep it that way.
- **Prefer structured feeds over HTML scraping** (RSS, the city24 JSON API). HTML scrape
  is the fallback. Alert on zero-results/parse-failure — don't fail silently.
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

1. MVP — ss.lv RSS + city24 JSON → dedupe/store → Telegram alerts.
2. Enrichment — commute, schools, flood, €/m².
3. Valuation — €/m² vs NĪTIS comparables → over/under-priced.
4. Scoring — hard filters + weighted-sum → ranked shortlist.
5. Auction watch — izsoles scrape + due-diligence checklist.
6. Dashboard + price history (SWA).

## Hypothesis

_Can an AI-assisted, multi-source pipeline surface fairly-priced, family-suitable homes
faster and with better judgment than manual portal-watching — enough to change which
property gets bought?_

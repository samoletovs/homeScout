# homeScout

homeScout is a property-intelligence pipeline for Baltic home-buying. It
combines listings, registered sale data, public geodata, deterministic scoring,
and Telegram delivery into a ranked decision aid.

## Research question

homeScout tests the nauroLabs question **"What's worth selling?"** Specifically,
it asks whether combining fragmented public and commercial data into timely,
explainable property advice creates more value than another listing alert.

## Why

Buying a family home in Mārupe / Rīga / Jūrmala means watching several portals, guessing
whether a price is fair, and reacting slowly. homeScout turns that into a monitored,
valued, ranked feed — a **decision aid, not just an alert bot**.

## What it does

1. **Ingest** new listings from ss.lv RSS + city24 JSON API + developer sites (deduped).
2. **Enrich** each with commute time, nearest school/kindergarten, flood flag.
3. **Value** — compare €/m² against nearby registered deals (VZD NĪTIS) → over/under-priced.
4. **Score** — hard filters + deterministic weighted-sum against family criteria.
5. **Auction watch** — surface izsoles.ta.gov.lv real-estate auctions + due-diligence checklist.
6. **Notify + dashboard** — ranked shortlist to Telegram; browsable board (SWA).

See [AGENTS.md](AGENTS.md) for the full build plan, data sources, and conventions.

## Stack

- Python 3.11 and Azure Functions v2
- Cosmos DB for durable state; SQLite for local development and tests
- Azure OpenAI for optional adviser text
- Telegram Bot API
- Bicep infrastructure

## Run locally

```bash
cd functions
pip install -r requirements.txt
python -m unittest discover ../tests
python ../scripts/run_once.py
```

The parser/scorer/store core is **stdlib-only** (tests need no network); `run_once`
does a real fetch and seeds the dedup store on first run.

## Structure

- `functions/` — Azure Functions (Python v2), timer-triggered pipeline
  - `sources.py` — portal adapters (ss.lv, city24; izsoles/NĪTIS stubs)
  - `parsers.py` — pure payload → `Listing` parsers
  - `enrich.py` / `geo.py` — geocode, nearest school/kindergarten, commute
  - `valuation.py` — €/m² vs area sold-deal medians (VZD NĪTIS)
  - `pipeline.py` — ingest → dedupe → store → enrich → value → notify
  - `scoring.py` — hard filters + weighted-sum (used from Phase 4)
  - `store.py` — SQLite dedup + price history + geocode cache
  - `models.py` — `Listing` / `Deal` / `ScoredListing`
- `infrastructure/` — Bicep (monitoring + Functions + Cosmos)
- `tests/` — 66 offline unit tests
- `scripts/` — `run_once.py`; `refresh_amenities.py` + `refresh_deals.py` (dataset refresh)

## Data and privacy

The engine and public reference datasets live here. Budgets, shortlisted
addresses, offers, mortgage figures, and other personal data stay outside the
repository. Runtime secrets go in
`functions/local.settings.json` / SWA App Settings (both git-ignored), never in the repo.

## Status

**Active scaffold; phases 1-4 built.** ss.lv + city24 ingest, dedupe, Telegram alerts, enriched with
commute / nearest school / kindergarten / €/m², each apartment flagged **under / fair /
over-priced** vs registered sold-deals (VZD NĪTIS), and listings **ranked by a weighted ⭐
score**. 66 passing tests. Off the default SWA-React golden path (Python Functions + Cosmos,
like agentMode/mindMe) - deviation documented in [AGENTS.md](AGENTS.md). Next:
auction watch (Phase 5) and dashboard (Phase 6).

## License

MIT

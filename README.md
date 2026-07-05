# homeScout

Property-intelligence pipeline for Baltic home-buying. It aggregates **new listings**
(ss.lv, city24, developer sites), values them against real **sold-deal** data
(VZD NĪTIS), watches court **auctions** (izsoles.ta.gov.lv), enriches each with
commute / school / flood signals from Latvia's open geodata, **scores** them against
family criteria, and pushes a ranked shortlist to Telegram.

> Lab experiment under [NauroLabs](https://naurolabs.com). Grew out of agentMode's
> `property_search` skill. Design + rationale: mindVault dig report
> `02_areas/agents/research/2026-07-04-ai-property-hunt-system-latvia.md`.

## Why

Buying a family home in Mārupe / Rīga / Jūrmala means watching several portals, guessing
whether a price is fair, and reacting slowly. homeScout turns that into a monitored,
valued, ranked feed — a **decision aid, not just an alert bot**.

## What it does (phased)

1. **Ingest** new listings from ss.lv RSS + city24 JSON API + developer sites (deduped).
2. **Enrich** each with commute time, nearest school/kindergarten, flood flag.
3. **Value** — compare €/m² against nearby registered deals (VZD NĪTIS) → over/under-priced.
4. **Score** — hard filters + deterministic weighted-sum against family criteria.
5. **Auction watch** — surface izsoles.ta.gov.lv real-estate auctions + due-diligence checklist.
6. **Notify + dashboard** — ranked shortlist to Telegram; browsable board (SWA).

See [AGENTS.md](AGENTS.md) for the full build plan, data sources, and conventions.

## Quick start (local)

```bash
cd functions
pip install -r requirements.txt
python -m unittest discover ../tests    # 19 offline tests must pass
python ../scripts/run_once.py           # live fetch (ss.lv + city24) → prints alertable listings
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
- `tests/` — 40 offline unit tests
- `scripts/` — `run_once.py`; `refresh_amenities.py` + `refresh_deals.py` (dataset refresh)

## Privacy

The **engine** lives here. **Personal data never does** — budget, shortlisted addresses,
offers and mortgage figures stay in the OneDrive `.me` vault
(`01_projects/2026-marupe-apartment-purchase/`). Runtime secrets go in
`functions/local.settings.json` / SWA App Settings (both git-ignored), never in the repo.

## Status

**Phases 1–4 built** — ss.lv + city24 ingest, dedupe, Telegram alerts, enriched with
commute / nearest school / kindergarten / €/m², each apartment flagged **under / fair /
over-priced** vs registered sold-deals (VZD NĪTIS), and listings **ranked by a weighted ⭐
score**. 42 passing tests. Off the default SWA-React golden path (Python Functions + Cosmos,
like agentMode/mindMe) — deviation documented in [AGENTS.md](AGENTS.md). Next: auction watch
(Phase 5) + dashboard (Phase 6).

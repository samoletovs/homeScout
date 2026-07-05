# homeScout — Agent Instructions

> Project-specific instructions for AI coding agents (Copilot, Codex, Claude Code).

## Project

Property-intelligence pipeline for a family buying a home in Mārupe / Rīga / Jūrmala.
Ingests new listings, values them against real sold-deal data, watches auctions, enriches,
scores, and alerts a ranked shortlist. Python Azure Functions (v2) + Cosmos + Telegram,
with an optional SWA dashboard. Grew out of agentMode's `property_search` skill.

## North star & delivery

homeScout is a **professional property adviser**, not just a notifier — it reasons about each
place (fair price vs the area, commute/airport, schools, pros/cons, what to check) and delivers
a **daily brief** of ranked matches. Delivery reuses the family's existing **ilitut.ilitam bot
(agentMode)** — same bot token (Key Vault) + family chat, no new bot. During transition,
agentMode's simpler `property_search` skill keeps running; homeScout runs alongside as the
advanced adviser and supersedes the old skill once trusted.

## Feedback, learning & language

- **Learning loop:** the family 👍/👎 + comments on listings via `feedback.ingest` (the
  channel-agnostic intake). Judgments *and* feedback are persisted; `store.taste_summary()`
  feeds the adviser so it weighs learned preferences over time. Test it now with
  `scripts/feedback.py <url> like "комментарий"`.
- **Language:** the family communicates in **Russian**; stored data stays **English**. The
  adviser writes its take in `COMM_LANGUAGE` (ru); inbound comments are translated to English
  (`translate.to_english`) before storage.
- **agentMode gate (wired):** homeScout exposes `POST /api/feedback` (function-key
  protected) and sends the top listings as individual **cards with 👍/👎 buttons**. In
  agentMode, `shared/homescout.py` captures a button tap or a text/voice **reply to a card**,
  infers sentiment (ru/en/lv/emoji), and POSTs to the endpoint → `feedback.record` →
  `ingest`. Enable it by setting `HOMESCOUT_FEEDBACK_URL` (URL incl. `?code=`) in agentMode;
  unset, the gate is inert. The endpoint and the daily timer share one SQLite store — but
  **durable cloud state needs Cosmos DB or a Dedicated/Premium plan** (serverless disks don't
  persist; see Deploy).

## Deploy — the durable-state decision (READ before deploying)

homeScout keeps its seen-state + learned knowledge in SQLite. **Serverless Functions plans do
not persist local disk** (Flex Consumption = 0 GB persisted; Linux Consumption is retired and
persists only with an explicitly mounted Azure Files share). A straight serverless deploy
would therefore lose dedup state and family feedback on every recycle — defeating the
“gets smarter over time” goal. Pick one path **before** deploying:

1. **Cosmos DB (recommended — golden path, free tier).** Move `store.py` behind its current
   interface to a Cosmos-backed implementation (listings / price_history / geocache / feedback
   as containers); keep SQLite for local dev + tests. Deploy the Function App on Flex
   Consumption. Durable, ~free, scales to zero. (This is the long-standing config.py TODO.)
2. **Dedicated (B1) / Premium plan.** Keep SQLite, mount the persistent HOME share, point
   `HOMESCOUT_DB` at it. Minimal code change, but ~€13+/month and always-on.

Until one is chosen, run the brief on demand with `scripts/run_once.py --preview --send`
(local, and durable on your own machine) — it already produces the real ranked brief.

## Build / test / verify

```bash
cd functions
pip install -r requirements.txt
python -m unittest discover ../tests    # MUST pass (parser/scorer/store are stdlib-only)
python ../scripts/run_once.py           # LIVE fetch: ss.lv + city24 → prints alertable listings
python ../scripts/run_once.py --preview # LIVE brief on demand (rank + advise top; --send to Telegram)
```

## Project structure

```
functions/
├── function_app.py   # Azure Functions entry (timer trigger → pipeline.run_once)
├── pipeline.py       # ingest → dedupe → store(seen) → enrich → value → notify
├── sources.py        # async fetchers: ss.lv RSS + city24 (curl_cffi); izsoles/NĪTIS stubs
├── parsers.py        # pure payload → Listing parsers (unit-tested)
├── enrich.py         # geocode (Nominatim) + nearest school/kindergarten (local OSM) + commute (ORS)
├── valuation.py      # €/m² vs area sold-deal medians (VZD NĪTIS) → under/fair/over
├── geo.py            # pure geo helpers: haversine, parsing, proximity score
├── store.py          # SQLite dedup / seen-state + price history + geocode cache
├── notify.py         # Telegram sender + message formatting
├── config.py         # feeds, target areas, enrichment endpoints, env
├── scoring.py        # hard filters + deterministic weighted-sum (used from Phase 4)
├── models.py         # Listing / Deal / ScoredListing (dataclasses, stdlib)
├── assets/           # committed datasets: lv_amenities.json (OSM), lv_deals.json (NĪTIS)
├── host.json
└── requirements.txt
infrastructure/main.bicep    # monitoring module + (TODO) Functions + Cosmos
tests/                       # parsers/store/notify/scoring/geo/enrich/valuation/feedback/adviser (57 tests)
scripts/run_once.py          # local runner: real run + --preview on-demand brief (live fetch)
scripts/refresh_amenities.py # refresh committed OSM amenities dataset
scripts/refresh_deals.py     # refresh committed NĪTIS valuation index
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
3. ✅ **Valuation (built)** — €/m² vs VZD NĪTIS area medians → under/fair/over-priced.
4. ✅ **Scoring (built)** — hard filters + weighted-sum → ranked, ⭐-scored shortlist.
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
- **Valuation is apartment-only and area-median** (VZD NĪTIS, 2025–2026): precise for
  Mārupe/Jūrmala (small, uniform) but only a rough guide for Rīga (city-wide median vs
  heterogeneous neighborhoods). Refresh with `scripts/refresh_deals.py`.
- **Flood risk** is not yet wired (Phase 2.1 — ĢEOLatvija WFS point-in-polygon).
- Telegram send is a no-op (logs alerts) until `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`
  are set.

## Hypothesis

_Can an AI-assisted, multi-source pipeline surface fairly-priced, family-suitable homes
faster and with better judgment than manual portal-watching — enough to change which
property gets bought?_

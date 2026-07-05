"""Refresh the committed sold-deal valuation index from VZD NĪTIS (data.gov.lv, CC BY 4.0).

Downloads recent yearly apartment-transaction CSVs, computes median €/m² per target area
(Rīga, Jūrmala, Mārupe), and writes functions/assets/lv_deals.json. Runtime valuation
reads only that committed index — no NĪTIS download at request time.

Usage:  python scripts/refresh_deals.py
"""
import csv
import datetime as dt
import io
import json
import os
import statistics
import sys
import zipfile

import httpx

OUT_PATH = os.path.join(os.path.dirname(__file__), "..", "functions", "assets", "lv_deals.json")
UA = {"User-Agent": "Mozilla/5.0 homeScout/0.1 (+https://github.com/samoletovs/homeScout)"}

# NĪTIS yearly apartment (telpu grupas) CSV ZIPs — recent window.
_BASE = "https://data.gov.lv/dati/dataset/f8a8a929-28d5-4f4f-85e9-062168cb4aba/resource/"
YEAR_ZIPS = {
    2025: _BASE + "4fe41171-3313-4db3-bb2b-dea1f7809a21/download/nitis_csv_2025.zip",
    2026: _BASE + "ae7a0df6-a246-48b3-a5f0-e394128f2bd9/download/nitis_csv_2026.zip",
}

# Column indices in the TG (apartment) CSV.
COL_PRICE = 9
COL_NOVADS, COL_PILSETA, COL_PAGASTS = 5, 6, 7
COL_SHARE_NUM, COL_SHARE_DEN = 33, 34
COL_AREA, COL_AREA_ALT = 39, 38  # Dzīvokļa kopplatība, fallback Telpu grupas platība


def bucket_of(novads: str, pilseta: str, pagasts: str):
    text = " ".join(v for v in (novads, pilseta, pagasts) if v and v != "NULL").lower()
    if "mārup" in text:
        return "Mārupe"
    if "jūrmala" in text:
        return "Jūrmala"
    if "rīga" in text:
        return "Rīga"
    return None


def _num(value: str):
    if value in ("", "NULL"):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def collect() -> dict:
    buckets: dict = {"Rīga": [], "Jūrmala": [], "Mārupe": []}
    for year, url in YEAR_ZIPS.items():
        resp = httpx.get(url, timeout=180, headers=UA, follow_redirects=True)
        resp.raise_for_status()
        archive = zipfile.ZipFile(io.BytesIO(resp.content))
        name = next(n for n in archive.namelist() if "TG" in n.upper() and n.lower().endswith(".csv"))
        reader = csv.reader(io.StringIO(archive.read(name).decode("utf-8-sig")), delimiter=";")
        next(reader, None)
        kept = 0
        for row in reader:
            if len(row) <= COL_AREA:
                continue
            num, den = row[COL_SHARE_NUM], row[COL_SHARE_DEN]
            if num not in ("", "NULL") and den not in ("", "NULL") and num != den:
                continue  # fractional-share deal — skip
            price = _num(row[COL_PRICE])
            area = _num(row[COL_AREA]) or _num(row[COL_AREA_ALT])
            if not price or not area or price < 10000 or area < 15:
                continue
            ppm2 = price / area
            if ppm2 < 300 or ppm2 > 8000:
                continue
            bucket = bucket_of(row[COL_NOVADS], row[COL_PILSETA], row[COL_PAGASTS])
            if bucket:
                buckets[bucket].append(ppm2)
                kept += 1
        print(f"{year}: {name} kept {kept}")
    return buckets


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    buckets = collect()
    out = {
        "source": "VZD NĪTIS via data.gov.lv (CC BY 4.0)",
        "generated": dt.date.today().isoformat(),
        "window_years": sorted(YEAR_ZIPS),
        "unit": "eur_per_m2_apartment",
        "buckets": {},
    }
    for name, values in buckets.items():
        if not values:
            continue
        quartiles = statistics.quantiles(values, n=4)
        out["buckets"][name] = {
            "median_ppm2": round(statistics.median(values), 1),
            "p25_ppm2": round(quartiles[0], 1),
            "p75_ppm2": round(quartiles[2], 1),
            "count": len(values),
        }
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as handle:
        json.dump(out, handle, ensure_ascii=False, indent=2)
    print("wrote", OUT_PATH, out["buckets"])


if __name__ == "__main__":
    main()

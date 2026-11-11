"""Build rates.json — today's gold, silver, USD and fuel prices for the app.

    python3 update_rates.py            # writes ./rates.json (keeps the previous file's history)

Runs a few times a day in GitHub Actions (see .github/workflows/update-rates.yml);
the app downloads the published rates.json. Standard library only. No API keys.

Sources
  Gold, silver : Tamil Nadu jewellers' daily board rate (one rate for the whole state —
                 what shops like GRT and Lalithaa quote), as listed by LiveChennai, https://www.livechennai.com/gold_silverrate.asp.
                 Excludes GST (3%) and making charges. The app shows this first.
                 Backup / national benchmark: IBJA (India Bullion and Jewellers Association),
                 https://ibjarates.com, read from the data the page embeds for its own charts.
  USD → INR    : ExchangeRate-API open access, https://open.er-api.com (attribution required:
                 "Rates By Exchange Rate API", shown in the app).
  Petrol/diesel: fuel.json in this folder, updated by hand when oil companies change the
                 price (official sites block automated reading, so they are not scraped).
"""
from __future__ import annotations

import html
import json
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "rates.json"
FUEL = HERE / "fuel.json"
IST = timezone(timedelta(hours=5, minutes=30))
UA = {"User-Agent": "TamilCalendarRates/1.0 (daily rate snapshot for a calendar app)"}
GRAMS_PER_SOVEREIGN = 8


def get(url: str) -> str:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def ibja() -> dict:
    page = get("https://ibjarates.com/")

    def series(input_id: str) -> dict:
        m = re.search(r'id="%s"\s+value="([^"]*)"' % input_id, page)
        if not m:
            raise ValueError(f"IBJA page layout changed: {input_id} not found")
        return json.loads(html.unescape(m.group(1)))

    gold, silver = series("HdnGold"), series("HdnSilver")

    def iso(label: str) -> str:
        return datetime.strptime(label, "%d/%m/%Y").date().isoformat()

    def last_two(values):
        return values[-1], (values[-2] if len(values) > 1 else None)

    g999, p999 = last_two(gold["purity999"])
    g916, p916 = last_two(gold["purity916"])
    s999, ps999 = last_two(silver["silverRate"])
    per_g = lambda v: None if v is None else round(v / 10, 2)  # IBJA gold is per 10 g
    return {
        "gold": {
            "date": iso(gold["labels"][-1]),
            "prevDate": iso(gold["labels"][-2]) if len(gold["labels"]) > 1 else None,
            "g24": per_g(g999), "g22": per_g(g916),
            "prev24": per_g(p999), "prev22": per_g(p916),
            "sovereign22": round(g916 / 10 * GRAMS_PER_SOVEREIGN),
            "source": "IBJA",
        },
        "silver": {
            "date": iso(silver["labels"][-1]),
            "perKg": s999, "prevKg": ps999,
            "perGram": round(s999 / 1000, 2),
            "source": "IBJA",
        },
        "history": {
            "dates": [iso(x) for x in gold["labels"][-7:]],
            "g22": [per_g(v) for v in gold["purity916"][-7:]],
        },
    }


def tamilnadu(ibja_g22: float | None) -> dict:
    page = get("https://www.livechennai.com/gold_silverrate.asp")

    def rows(table_class: str) -> list[list[str]]:
        m = re.search(r'<table[^>]*class="[^"]*\b%s\b[^"]*"[^>]*>(.*?)</table>' % table_class, page, re.S)
        if not m:
            raise ValueError(f"LiveChennai layout changed: table {table_class} not found")
        out = []
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", m.group(1), re.S):
            cells = [re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", td))).strip()
                     for td in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)]
            if cells and re.match(r"\d{2}/[A-Za-z]{3}/\d{4}$", cells[0]):
                out.append(cells)
        if len(out) < 2:
            raise ValueError(f"LiveChennai table {table_class}: too few rows")
        return out

    def iso(label: str) -> str:
        return datetime.strptime(label, "%d/%b/%Y").date().isoformat()

    def num(cell: str) -> float:
        return float(re.match(r"[\d,]+(?:\.\d+)?", cell).group(0).replace(",", ""))

    gold = rows("gold-rates")      # date | 24K 1g | 24K 8g | 22K 1g | 22K 8g
    silver = rows("silver-rates")  # date | 1g | 1kg
    g22, p22 = num(gold[0][3]), num(gold[1][3])
    g24, p24 = num(gold[0][1]), num(gold[1][1])
    sg, psg = num(silver[0][1]), num(silver[1][1])
    # Guard against a mis-read table: the shop rate stays within a few % of the IBJA rate.
    if ibja_g22 and not 0.9 < g22 / ibja_g22 < 1.1:
        raise ValueError(f"LiveChennai 22K {g22} too far from IBJA {ibja_g22}")
    if not (g24 > g22 > 1000 and 10 < sg < 10000):
        raise ValueError(f"LiveChennai values look wrong: {g24} {g22} {sg}")
    return {
        "date": iso(gold[0][0]), "prevDate": iso(gold[1][0]),
        "g22": g22, "prev22": p22, "g24": g24, "prev24": p24,
        "sovereign22": round(g22 * GRAMS_PER_SOVEREIGN),
        "silverDate": iso(silver[0][0]), "silverGram": sg, "silverPrev": psg,
        "source": "LiveChennai (Tamil Nadu jewellers' board rate)",
    }


def usd(previous: dict | None) -> dict:
    d = json.loads(get("https://open.er-api.com/v6/latest/USD"))
    if d.get("result") != "success":
        raise ValueError(f"open.er-api: {d.get('result')}")
    inr = round(d["rates"]["INR"], 2)
    date = datetime.fromtimestamp(d["time_last_update_unix"], IST).date().isoformat()
    prev = None
    if previous:  # keep yesterday's value for the ▲▼ arrow
        prev = previous.get("prev") if previous.get("date") == date else previous.get("inr")
    return {"date": date, "inr": inr, "prev": prev, "source": "Rates By Exchange Rate API"}


def main() -> int:
    old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    out = {"version": 1, "generatedAt": datetime.now(IST).isoformat(timespec="minutes")}
    errors = []
    try:
        out.update(ibja())
    except Exception as e:  # keep yesterday's numbers rather than publish nothing
        errors.append(f"gold/silver: {e}")
        for k in ("gold", "silver", "history"):
            if k in old:
                out[k] = old[k]
    try:
        out["tn"] = tamilnadu((out.get("gold") or {}).get("g22"))
    except Exception as e:
        errors.append(f"tn: {e}")
        if "tn" in old:
            out["tn"] = old["tn"]
    try:
        out["usd"] = usd(old.get("usd"))
    except Exception as e:
        errors.append(f"usd: {e}")
        if "usd" in old:
            out["usd"] = old["usd"]
    if FUEL.exists():
        out["fuel"] = json.loads(FUEL.read_text(encoding="utf-8"))
    if errors:
        out["errors"] = errors

    new_body = {k: v for k, v in out.items() if k != "generatedAt"}
    old_body = {k: v for k, v in old.items() if k != "generatedAt"}
    if new_body == old_body:
        print("no change")
        return 0
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False)[:400])
    for e in errors:
        print("!", e, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

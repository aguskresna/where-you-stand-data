"""World Development Indicators via the World Bank API, keeping only indicators licensed CC BY.

WDI is CC BY 4.0 unless an indicator's metadata says otherwise (some come from partners with their own
terms). Each indicator's License_Type is checked through the metadata API and anything else is skipped.
To keep an indicator after checking its terms yourself, list it in
pipeline/manual/worldbank_wdi/license_overrides.json as {"CODE": "why it's allowed"}.
"""

from __future__ import annotations

import json

from ..common import PipelineError

SOURCE = "worldbank_wdi"
INDICATORS = {
    "PA.NUS.PRVT.PP": "PPP conversion factor, private consumption (LCU per international $)",
    "FP.CPI.TOTL": "Consumer price index (2010 = 100)",
    "NY.GDP.PCAP.PP.KD": "GDP per capita, PPP (constant 2021 international $)",
    "EG.ELC.ACCS.ZS": "Access to electricity (% of population)",
    "IT.NET.USER.ZS": "Individuals using the Internet (% of population)",
}
API = "https://api.worldbank.org/v2"


def version(ctx) -> str:
    """WDI's own last-updated date, so the job rebuilds only after a new WDI release."""
    body = ctx.fetch_json(f"{API}/sources/2", {"format": "json"})
    try:
        return str(body[1][0].get("lastupdated"))
    except (IndexError, KeyError, TypeError):
        return json.dumps(body)[:200]


def find_license(meta) -> str | None:
    """The License_Type value anywhere in the metadata response, or None."""
    if isinstance(meta, dict):
        if str(meta.get("id", "")).lower() == "license_type" and isinstance(meta.get("value"), str):
            return meta["value"]
        for v in meta.values():
            found = find_license(v)
            if found:
                return found
    elif isinstance(meta, list):
        for v in meta:
            found = find_license(v)
            if found:
                return found
    return None


def allowed(license_text: str | None) -> bool:
    return bool(license_text) and "CC BY" in license_text.upper().replace("-", " ") and "NC" not in license_text.upper()


def overrides(ctx) -> dict:
    path = ctx.manual_dir / "license_overrides.json"
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def fetch_series(ctx, code: str, first: int = 1990, last: int | None = None) -> dict:
    last = last or ctx.today.year
    out: dict[str, dict[str, float]] = {}
    page, pages = 1, 1
    while page <= pages:
        body = ctx.fetch_json(f"{API}/country/all/indicator/{code}", {"format": "json", "per_page": 20000, "date": f"{first}:{last}", "page": page})
        if not isinstance(body, list) or len(body) < 2:
            raise PipelineError(f"Unexpected response for {code}: {str(body)[:200]}")
        pages = int(body[0].get("pages", 1))
        for row in body[1] or []:
            iso, value = row.get("countryiso3code"), row.get("value")
            if iso and value is not None:
                out.setdefault(iso, {})[str(row["date"])] = round(float(value), 4)
        page += 1
    return out


def build(ctx) -> None:
    keep = overrides(ctx)
    indicators = {}
    for code, label in INDICATORS.items():
        meta = ctx.fetch_json(f"{API}/sources/2/series/{code}/metadata", {"format": "json"})
        lic = find_license(meta)
        if not allowed(lic) and code not in keep:
            ctx.log(f"  skipped {code}: license is {lic or 'not stated'}")
            continue
        indicators[code] = {"label": label, "license": lic or f"override: {keep.get(code)}", "series": fetch_series(ctx, code)}
    if not indicators:
        raise PipelineError("No indicator passed the license check")
    ctx.write("world.wdi", {"indicators": indicators}, year=ctx.today.year,
              note="Only indicators whose metadata license is CC BY (or listed in license_overrides.json).")

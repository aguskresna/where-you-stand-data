"""BLS Consumer Price Index (CPI-U, U.S. city average): the eight major groups' 12-month change and weight.

Index values come from the BLS public API v1 (no key). The 12-month change is worked out from the
unadjusted indexes the way BLS does it and rounded to one decimal of a percent, like BLS publishes it.
The latest month whose index and the index twelve months earlier are both published is used (there
is no October 2025 index because of the 2025 lapse in appropriations, so no 12-month change for
October 2026 either).

Relative importance weights are only published as a table on www.bls.gov, which refuses the
pipeline's requests (HTTP 403), so that table is saved by hand (see HOW). Without it the dataset is
built without weights, and the app starts from an even split.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

from ..common import PipelineError

SOURCE = "bls_cpi"
API = "https://api.bls.gov/publicAPI/v1/timeseries/data/"
ALL_ITEMS = "SA0"
GROUPS = {
    "SAF": "Food and beverages",
    "SAH": "Housing",
    "SAA": "Apparel",
    "SAT": "Transportation",
    "SAM": "Medical care",
    "SAR": "Recreation",
    "SAE": "Education and communication",
    "SAG": "Other goods and services",
}
WEIGHTS_YEAR = 2025  # December 2025 weights, published early in 2026; move on when BLS publishes the next table
WEIGHTS_FILES = [f"relative-importance-{WEIGHTS_YEAR}.xlsx", f"relative-importance-{WEIGHTS_YEAR}.htm"]
MANUAL = WEIGHTS_FILES
PAGE = f"https://www.bls.gov/cpi/tables/relative-importance/{WEIGHTS_YEAR}.htm"
HOW = (f"Open {PAGE} in a browser and save either the Excel version of the table as "
       f"pipeline/manual/bls_cpi/{WEIGHTS_FILES[0]} or the page itself (HTML only) as pipeline/manual/bls_cpi/{WEIGHTS_FILES[1]}.")


def series_id(code: str) -> str:
    return f"CUUR0000{code}"  # CPI-U, U.S. city average, not seasonally adjusted


def fetch(ctx, code: str) -> list[dict]:
    body = ctx.fetch_json(API + series_id(code))
    if body.get("status") != "REQUEST_SUCCEEDED":
        raise PipelineError(f"BLS API refused {series_id(code)}: {body.get('message')}")
    return body["Results"]["series"][0]["data"]


def monthly(data: list[dict]) -> dict[tuple[int, int], float]:
    """{(year, month): index} for the published monthly values (annual averages and gaps left out)."""
    out = {}
    for row in data:
        m = re.fullmatch(r"M(\d\d)", row.get("period", ""))
        if not m or int(m.group(1)) > 12:
            continue
        try:
            out[(int(row["year"]), int(m.group(1)))] = float(row["value"])
        except (TypeError, ValueError):
            continue  # '-' : not published
    return out


def twelve_month(series: dict[str, dict[tuple[int, int], float]]) -> tuple[tuple[int, int], dict[str, float]]:
    """The latest month where every series has both that month and the same month a year earlier."""
    months = sorted(set.intersection(*(set(s) for s in series.values())), reverse=True)
    for y, m in months:
        if all((y - 1, m) in s for s in series.values()):
            return (y, m), {code: round(round((s[(y, m)] / s[(y - 1, m)] - 1) * 100, 1) / 100, 3) for code, s in series.items()}
    raise PipelineError("No month has a 12-month change for every CPI group")


# ---------------------------------------------------------------- relative importance


class _Rows(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows, self._row, self._cell = [], None, None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._row is not None and self._cell is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def table_rows(path: Path) -> list[list[str]]:
    if path.suffix.lower() in (".htm", ".html"):
        p = _Rows()
        p.feed(path.read_text(encoding="utf-8", errors="replace"))
        return p.rows
    import pandas as pd

    rows = []
    for _, sheet in pd.read_excel(path, sheet_name=None, header=None, dtype=str).items():
        rows += [["" if v is None or str(v) == "nan" else str(v).strip() for v in r] for r in sheet.itertuples(index=False)]
    return rows


def _label(text: str) -> str:
    return re.sub(r"\(\d+\)|\s+", " ", text).strip().rstrip(".").lower()


def weights_from(rows: list[list[str]]) -> dict[str, float]:
    """CPI-U relative importance (as a share) of All items and the eight groups.

    The table lists the expenditure category, then the CPI-U and CPI-W figures; the first number after
    the label is the CPI-U one. Each group is taken from its first row (the group itself, before its items).
    """
    wanted = {_label(v): k for k, v in {ALL_ITEMS: "All items", **GROUPS}.items()}
    out = {}
    for row in rows:
        for i, cell in enumerate(row):
            code = wanted.get(_label(cell))
            if code and code not in out:
                for v in row[i + 1:]:
                    try:
                        out[code] = float(v.replace(",", "")) / 100
                        break
                    except ValueError:
                        continue
                break
    missing = [GROUPS.get(c, "All items") for c in [ALL_ITEMS, *GROUPS] if c not in out]
    if missing:
        raise PipelineError(f"The relative importance table has no CPI-U figure for {', '.join(missing)}")
    total = sum(out[c] for c in GROUPS)
    if abs(out[ALL_ITEMS] - 1) > 0.001 or abs(total - 1) > 0.002:
        raise PipelineError(f"The relative importance figures don't add up (All items {out[ALL_ITEMS]:.4f}, groups {total:.4f})")
    return {c: round(out[c], 5) for c in GROUPS}


def weights_file(ctx) -> Path | None:
    for name in WEIGHTS_FILES:
        for folder in (ctx.manual_dir, ctx.raw):
            if (folder / name).exists():
                return folder / name
    return None


# ---------------------------------------------------------------- build


def version(ctx) -> str:
    """The newest all-items month in the API (one request), so the job rebuilds after each release."""
    m = monthly(fetch(ctx, ALL_ITEMS))
    return "%d-%02d" % max(m) if m else "none"


def build_from(ctx, series: dict[str, dict[tuple[int, int], float]], weights: dict[str, float] | None) -> None:
    (y, m), change = twelve_month(series)
    groups = {}
    for code, label in GROUPS.items():
        groups[code] = {"label": label, "change": change[code], **({"weight": weights[code]} if weights else {})}
    note = f"CPI-U, U.S. city average, 12 months to {y}-{m:02d}."
    note += f" Weights: relative importance, December {WEIGHTS_YEAR}." if weights else " Relative importance weights not saved yet."
    ctx.write("us.bls.cpi", {"asOf": f"{y}-{m:02d}", "overall": change[ALL_ITEMS], "groups": groups}, year=y, note=note)


def build(ctx) -> None:
    series = {code: monthly(fetch(ctx, code)) for code in [ALL_ITEMS, *GROUPS]}
    path = weights_file(ctx)
    if path is None:
        ctx.log(f"  no relative importance table: building without weights. {HOW}")
    build_from(ctx, series, weights_from(table_rows(path)) if path else None)

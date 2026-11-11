"""BLS Employment Projections: base and projected employment and percent change by occupation.

www.bls.gov refuses the pipeline's requests (HTTP 403, "Access Denied"), so the occupation.xlsx file
can't be fetched. The same table (title, SOC code, employment in the base and projection years in
thousands, percent change) is published as a web page on data.bls.gov, which does answer, and is read
from there. A copy saved by hand as pipeline/manual/bls_projections/occupationProj.html is used first.
"""

from __future__ import annotations

import hashlib
import html
import re
from html.parser import HTMLParser

from ..common import PipelineError

SOURCE = "bls_projections"
URL = "https://data.bls.gov/projections/occupationProj"
FILE = "occupationProj.html"


class _Rows(HTMLParser):
    """Every table row as a list of its cells' text (example job titles inside cells are dropped)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []
        elif tag == "p" and dict(attrs).get("class") == "laytitles":
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._row is not None and self._cell is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None
        elif tag == "p" and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if self._cell is not None and not self._skip:
            self._cell.append(data)


def _number(text: str) -> float:
    t = text.replace(",", "").replace("$", "").strip()
    if not re.fullmatch(r"-?\d+(\.\d+)?", t):
        raise ValueError(text)
    return float(t)


def parse(text: str) -> dict:
    """The dataset from the page: {baseYear, projYear, all:{change}, occupations:{SOC: {...}}}."""
    years = re.search(r"Employment Percent Change,\s*(\d{4})\s*-\s*(\d{4})", html.unescape(text))
    if not years:
        raise PipelineError("The projections page has no 'Employment Percent Change, YYYY-YYYY' column")
    base_year, proj_year = int(years.group(1)), int(years.group(2))
    p = _Rows()
    p.feed(text)
    occupations, total = {}, None
    for row in p.rows:
        # Title, code, base employment, projected employment, change, percent change, openings, ...
        if len(row) < 6 or not re.fullmatch(r"\d{2}-\d{4}", row[1]):
            continue
        try:
            base, proj, pct = _number(row[2]), _number(row[3]), _number(row[5])
        except ValueError:
            continue  # a value the page doesn't publish
        entry = {"title": row[0].replace("Show/hide Example Job Titles", "").strip(),
                 "base": round(base * 1000), "proj": round(proj * 1000), "change": round(pct / 100, 4)}
        if row[1] == "00-0000":
            total = entry
        else:
            occupations[row[1]] = entry
    if total is None or len(occupations) < 500:
        raise PipelineError(f"The projections page layout changed: found {len(occupations)} occupations and {'a' if total else 'no'} total row")
    return {"baseYear": base_year, "projYear": proj_year, "all": {"change": total["change"]}, "occupations": dict(sorted(occupations.items()))}


def read_page(ctx, refresh: bool = False) -> str:
    path = ctx.manual_dir / FILE
    if not path.exists():
        path = ctx.download(URL, FILE, refresh=refresh)
    return path.read_text(encoding="utf-8", errors="replace")


def version(ctx) -> str:
    """A hash of the table itself (the page has no ETag or Last-Modified), so revisions are noticed too."""
    data = parse(read_page(ctx, refresh=not (ctx.manual_dir / FILE).exists()))
    return hashlib.sha256(repr(data).encode("utf-8")).hexdigest()


def build_from(ctx, text: str) -> None:
    data = parse(text)
    ctx.write("us.bls.projections", data, year=data["baseYear"],
              note=f"BLS projections {data['baseYear']}-{data['projYear']}; change is the published percent change.")


def build(ctx) -> None:
    build_from(ctx, read_page(ctx))

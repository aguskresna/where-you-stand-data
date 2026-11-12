"""CIA World Factbook, final edition (public domain): religion shares by country.

The CIA stopped publishing the Factbook in February 2026. Its last edition is dated 22 January 2026
(the archived front page of 4 February 2026 still reads "Edition: Jan 22, 2026"). The figures come
from the Factbook's own "Religions" field data (page-data.json behind cia.gov/the-world-factbook/
field/religions/), as archived by the Wayback Machine on 28 January 2026, after that edition went up.
Countries are matched to ISO codes with the Factbook's own Country Data Codes page (archived
1 February 2026).

Each entry is free text such as "Protestant 46.5%, Roman Catholic 20.8%, ... (2014 est.)". Every
top-level item must read "<label> <number>%"; items given only as "<1%" are left out (no single
figure), and a country with any other item (a range, a name without a figure) is left out entirely
rather than shown in part. Breakdowns in brackets after a figure, and notes, are dropped.
"""

from __future__ import annotations

import html
import json
import re

from ..common import PipelineError

SOURCE = "cia_factbook"
EDITION = "2026-01-22"
WAYBACK = "https://web.archive.org/web/"
RELIGIONS_URL = WAYBACK + "20260128191807/https://www.cia.gov/the-world-factbook/page-data/field/religions/page-data.json"
MIN_COUNTRIES = 150  # the final edition parses to about 210; far fewer means the text or layout changed
CODES_URL = WAYBACK + "20260201102200/https://www.cia.gov/the-world-factbook/references/country-data-codes/"


def version(ctx) -> str:
    """The Factbook is frozen: rebuild only when this module changes the edition it reads."""
    return f"final edition {EDITION}: {RELIGIONS_URL} {CODES_URL}"


def build(ctx) -> None:
    religions = json.loads(ctx.download(RELIGIONS_URL, "religions-page-data-20260128.json").read_text(encoding="utf-8"))
    codes = ctx.download(CODES_URL, "country-data-codes-20260201.html").read_text(encoding="utf-8")
    build_from(ctx, religions, codes)


def iso_codes(page: str) -> dict[str, str]:
    """Factbook name -> ISO 3166 alpha-3, from the Country Data Codes table ('AF|AFG|004')."""
    out = {}
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.S):
        cells = [html.unescape(re.sub(r"<[^>]+>", "", c)).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        if len(cells) >= 3:
            parts = cells[2].split("|")
            if len(parts) == 3 and re.fullmatch(r"[A-Z]{3}", parts[1]):
                out[cells[0]] = parts[1]
    if len(out) < 200:
        raise PipelineError(f"Only {len(out)} ISO codes found on the Country Data Codes page: its layout changed")
    return out


def split_top(text: str) -> list[str]:
    """Splits on commas that aren't inside brackets."""
    parts, depth, cur = [], 0, ""
    for ch in text:
        depth += ch == "("
        depth -= ch == ")"
        if ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    return [p.strip() for p in parts if p.strip()]


ITEM = re.compile(r"^(?P<label>.*?\S)\s+(?P<lt><\s*)?(?P<pct>\d*\.?\d+)\s*%?(?:\s*\(.*\))?$")
NUMBER_ONLY = re.compile(r"^\d*\.?\d+\s*%$")
YEAR = re.compile(r"\s*\(((?:\d{4}|\d{4}-\d{2,4})(?: est\.)?)\)\s*$")


def _top_level_cut(text: str, sep: str) -> str:
    """Text up to the first sep that isn't inside brackets."""
    depth = 0
    for i, ch in enumerate(text):
        depth += ch == "("
        depth -= ch == ")"
        if ch == sep and depth == 0:
            return text[:i]
    return text


def parse(formatted: str) -> tuple[list, str | None] | None:
    """[[label, percent], ...] and the year note from one entry, or None if any item has no single figure.

    Tidies only what is unambiguous in the Factbook's text: a clause after ';' (the "less than 1%: ..."
    lists and notes) is dropped like other below-1% items; a figure split from its label by a stray
    comma ("Muslim, 1.3%") is joined back; a bracket standing alone after an item is dropped; and
    label words split by commas are joined when the next item continues them with "or"/"and".
    """
    text = html.unescape(re.split(r"<br\s*/?>", formatted)[0]).replace(" ", " ")
    text = re.sub(r"<[^>]+>", "", text).strip()
    m = YEAR.search(text)
    year = m.group(1) if m else None
    if m:
        text = text[: m.start()]
    text = _top_level_cut(text, ";").strip()
    parts: list[str] = []
    for part in split_top(text):
        if parts and NUMBER_ONLY.match(part) and not ITEM.match(parts[-1]):
            parts[-1] = f"{parts[-1]} {part}"
        elif parts and part.startswith("(") and part.endswith(")"):
            continue
        else:
            parts.append(part)
    groups, pending = [], []
    for part in parts:
        item = ITEM.match(part)
        if not item:
            pending.append(part)
            continue
        label = item.group("label").strip()
        if pending:
            if not re.match(r"(or|and) ", label):
                return None
            label = ", ".join(pending + [label])
            pending = []
        if item.group("lt"):
            continue
        groups.append([label, float(item.group("pct"))])
    if pending or not groups or sum(p for _, p in groups) > 102:
        return None
    return groups, year


def build_from(ctx, religions: dict, codes_page: str) -> None:
    try:
        nodes = religions["result"]["data"]["fields"]["nodes"]
    except (KeyError, TypeError) as e:
        raise PipelineError("The archived Religions page-data has a new layout") from e
    iso = iso_codes(codes_page)
    countries, skipped = {}, []
    for n in nodes:
        name, code = n.get("placeName"), iso.get(n.get("placeName"))
        parsed = parse(n.get("formatted") or "")
        if not code or not parsed:
            skipped.append(name)
            continue
        groups, year = parsed
        countries[code] = {"name": name, "groups": groups, **({"year": year} if year else {})}
    if len(countries) < MIN_COUNTRIES:
        raise PipelineError(f"Only {len(countries)} countries parsed from the Religions field")
    ctx.log(f"  {len(countries)} countries; left out {len(skipped)}: {', '.join(map(str, skipped))}")
    ctx.write("world.factbook.religion", {"countries": dict(sorted(countries.items()))}, year=EDITION,
              citation={"title": "The World Factbook: Religions (final edition, 22 January 2026; archived copy)", "url": RELIGIONS_URL.replace("page-data/", "").replace("page-data.json", "")},
              note="The CIA stopped publishing The World Factbook in February 2026; these figures are frozen at its final edition of "
                   "22 January 2026, and each country's figure comes from its own survey or estimate year. Items given only as "
                   "'less than' a figure are left out, as are countries listed without a single figure for every group.")

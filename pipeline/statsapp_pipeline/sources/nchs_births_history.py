"""US births and total fertility rate by year, from the NCHS "Births: Final Data" reports (public domain).

NCHS publishes these tables only inside the National Vital Statistics Reports (PDF), so the text of
two reports is read:
  - the newest "Births: Final Data for <year>" linked from https://www.cdc.gov/nchs/nvss/births.htm:
    "Table 1. Births and birth rates: United States, 2010-<year> ..." (number of births) and
    "Table 2. Birth rates, by age of mother: United States, 2010-<year> ..." (total fertility rate);
  - "Births: Final Data for 2015" (NVSR vol. 66, no. 1), whose Table 1 (births, 1940-2015) and Table 4
    (total fertility rate, 1970-2015) reach back further. Rates for 2001-2009 there already use the
    populations revised after the 2010 census.
Only the "All races" rows are used. Where both reports have a year, the newer report wins. Years are
written only when NCHS gives both figures, so the series runs from 1970.
"""

from __future__ import annotations

import io
import re

from ..common import PipelineError

SOURCE = "nchs_births_history"
PAGE = "https://www.cdc.gov/nchs/nvss/births.htm"
HISTORY = "https://www.cdc.gov/nchs/data/nvsr/nvsr66/nvsr66_01.pdf"
HISTORY_YEAR = 2015

BIRTHS_TITLE = re.compile(r"^Table (\d+)\. Births and birth rates\b", re.I)
TFR_TITLE = re.compile(r"^Table (\d+)\. Birth rates, by age of mother: United States,", re.I)
ROW = re.compile(r"^\s*(\d{4,7})\S*?\s*(?:\.\s*)+\s*(\d[\d,]*(?:\.\d+)?)\b")


# ---------------------------------------------------------------- finding the reports


def latest_report(ctx) -> tuple[int, str]:
    """(data year, PDF url) of the newest 'Births: Final Data for <year>' linked from the NVSS births page."""
    html = ctx.download(PAGE, "births.html", refresh=True).read_text(encoding="utf-8", errors="replace")
    found = {}
    for href, year in re.findall(r'href="([^"]+\.pdf)"[^>]*>\s*Births:\s*Final\s+Data\s+for\s+(\d{4})', html, flags=re.I):
        url = href if href.startswith("http") else "https://www.cdc.gov" + href
        found[int(year)] = url
    if not found:
        raise PipelineError(f"No 'Births: Final Data for <year>' link on {PAGE}")
    year = max(found)
    return year, found[year]


def watch(ctx) -> list[str]:
    return [latest_report(ctx)[1], HISTORY]


# ---------------------------------------------------------------- reading the report text


def pdf_text(path) -> str:
    from pypdf import PdfReader

    with open(path, "rb") as f:
        reader = PdfReader(io.BytesIO(f.read()))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def report_year(text: str) -> int | None:
    m = re.search(r"Births:\s*Final\s+Data\s+for\s+(\d{4})", text, re.I)
    return int(m.group(1)) if m else None


def year_of(run: str) -> int | None:
    """The year in a row label with a footnote number glued on: '2015', '31984' (note 3), '19623' (note 3)."""
    for cand in (run[:4], run[-4:]):
        if 1900 <= int(cand) <= 2099:
            return int(cand)
    return None


def table_lines(text: str, title: re.Pattern) -> list[str]:
    """The lines of the first table whose title matches, including its continuation pages."""
    lines = text.splitlines()
    start = next((i for i, l in enumerate(lines) if title.match(l.strip())), None)
    if start is None:
        raise PipelineError(f"No table matching {title.pattern!r}")
    number = title.match(lines[start].strip()).group(1)
    out = []
    for l in lines[start:]:
        m = re.match(r"^Table (\w+)\.", l.strip())
        if m and m.group(1) != number:
            break
        out.append(l)
    return out


def all_races_column(lines: list[str]) -> dict[int, str]:
    """The first figure on each year row of the first block ('All races'), newest year first.

    The block ends where the years start again from the top (the next race group)."""
    out: dict[int, str] = {}
    last = None
    for l in lines:
        m = ROW.match(l)
        if not m:
            continue
        year = year_of(m.group(1))
        if year is None:
            continue
        if last is not None and year > last:
            break
        last = year
        out.setdefault(year, m.group(2))
    if not out:
        raise PipelineError("No year rows found in the table")
    return out


def series(text: str) -> tuple[dict[int, int], dict[int, float]]:
    """({year: births}, {year: total fertility rate per woman}) from one report's text."""
    births = {y: int(v.replace(",", "")) for y, v in all_races_column(table_lines(text, BIRTHS_TITLE)).items()}
    tfr_lines = table_lines(text, TFR_TITLE)
    if not any("total fertility" in l.lower() for l in tfr_lines[:12]):
        raise PipelineError("The birth rates table has no total fertility rate column")
    tfr = {y: round(float(v.replace(",", "")) / 1000, 5) for y, v in all_races_column(tfr_lines).items()}
    for y, b in births.items():
        if not 1_000_000 < b < 6_000_000:
            raise PipelineError(f"{y}: {b} births doesn't look like a US total")
    for y, t in tfr.items():
        if not 1.0 < t < 4.0:
            raise PipelineError(f"{y}: total fertility rate {t} doesn't look right")
    return births, tfr


# ---------------------------------------------------------------- building


def build(ctx) -> None:
    year, url = latest_report(ctx)
    latest = ctx.download(url, url.rsplit("/", 1)[-1])
    history = ctx.download(HISTORY, HISTORY.rsplit("/", 1)[-1])
    build_from(ctx, pdf_text(latest), pdf_text(history), expect_year=year)


def build_from(ctx, latest_text: str, history_text: str, expect_year: int | None = None) -> None:
    year = report_year(latest_text)
    if year is None or (expect_year and year != expect_year):
        raise PipelineError(f"The newest report is for {year}, expected {expect_year}")
    if report_year(history_text) != HISTORY_YEAR:
        raise PipelineError(f"The history report isn't 'Births: Final Data for {HISTORY_YEAR}'")
    hb, ht = series(history_text)
    lb, lt = series(latest_text)
    if max(lb) != year or max(lt) != year:
        raise PipelineError(f"The {year} report's tables end in {max(lb)} and {max(lt)}")
    for name, old, new in (("births", hb, lb), ("total fertility rate", ht, lt)):
        changed = [y for y in sorted(set(old) & set(new)) if abs(old[y] - new[y]) > 1e-9]
        if changed:
            ctx.log(f"  {name} revised in the {year} report for {changed}; using the newer figures")
    births, tfr = {**hb, **lb}, {**ht, **lt}
    years = sorted(set(births) & set(tfr))
    gaps = [y for y in range(years[0], years[-1] + 1) if y not in years]
    if gaps:
        raise PipelineError(f"Years without both figures: {gaps}")
    out = {str(y): {"births": births[y], "tfr": tfr[y]} for y in years}
    ctx.write("us.nchs.births_history", {"years": out}, year=year,
              note=f"Registered births and total fertility rate (children per woman), {years[0]}-{years[-1]}, from Births: Final Data for {year} and for {HISTORY_YEAR}.")

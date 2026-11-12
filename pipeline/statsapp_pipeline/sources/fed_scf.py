"""Survey of Consumer Finances (Federal Reserve Board): household wealth, retirement savings and debt.

Reads the public summary extract (SCFP<year>.csv), which has five implicates (rows) per family. All
five are stacked with their weight WGT; in the summary extract WGT is already the full-sample weight
divided by five (each implicate sums to the number of US families), so the stacked rows sum to the
population once. Percentiles don't depend on the scale of the weights anyway.

A group is published only when it has at least MIN_RECORDS different families (YY1), not rows.
Dollar figures are in dollars of the survey year, as the Fed publishes them.
"""

from __future__ import annotations

import zipfile

import pandas as pd

from ..common import SCF_BANDS, PipelineError, band_of, by_groups, round_to, weighted_quantiles, weighted_share

SOURCE = "fed_scf"
FILES = "https://www.federalreserve.gov/econres/files/"
PAGE = "https://www.federalreserve.gov/econres/scfindex.htm"
FIRST_WAVE = 2025  # the newest wave when this was written; later waves are found by checking FILES
COLUMNS = ["YY1", "Y1", "WGT", "AGE", "NETWORTH", "RETQLIQ", "DEBT", "MRTHEL", "EDN_INST", "VEH_INST", "CCBAL", "RESDBT", "OTHLOC", "OTH_INST", "ODEBT"]

# The Fed's debt categories, grouped as the app asks for them. 'other' is everything else the Fed
# counts in DEBT: other residential property, other lines of credit, other installment loans, other debt.
TYPES = {
    "mortgage": ("Mortgage and home equity", ["MRTHEL"]),
    "education": ("Student loans", ["EDN_INST"]),
    "vehicle": ("Car loans", ["VEH_INST"]),
    "card": ("Credit cards", ["CCBAL"]),
    "other": ("Other debt", ["RESDBT", "OTHLOC", "OTH_INST", "ODEBT"]),
}


def url(year: int) -> str:
    return f"{FILES}scfp{year}excel.zip"


def latest_wave(ctx) -> int:
    """The newest survey year whose summary extract is published (the survey runs every three years)."""
    year = FIRST_WAVE
    while ctx.exists(url(year + 3)):
        year += 3
    return year


def watch(ctx) -> list[str]:
    year = latest_wave(ctx)
    return [url(year), url(year + 3)]  # the next wave's file appearing changes the fingerprint


def build(ctx) -> None:
    year = latest_wave(ctx)
    path = ctx.download_or_manual(url(year), f"scfp{year}excel.zip", PAGE)
    with zipfile.ZipFile(path) as z:
        name = next((n for n in z.namelist() if n.lower().endswith(".csv")), None)
        if not name:
            raise PipelineError(f"No CSV inside {path.name}")
        with z.open(name) as f:
            df = pd.read_csv(f, usecols=lambda c: c.upper() in COLUMNS)
    df.columns = [c.upper() for c in df.columns]
    build_from(ctx, df, year)


def build_from(ctx, df: pd.DataFrame, year: int) -> None:
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        raise PipelineError(f"The SCF summary extract has no {missing}")
    d = df[df["WGT"] > 0].copy()
    d["band"] = band_of(d["AGE"], SCF_BANDS)
    d["w"] = d["WGT"]
    dims = {"band": SCF_BANDS}
    total_check = sum(d[c] for _, cols in TYPES.values() for c in cols)
    if (total_check - d["DEBT"]).abs().max() > 1:
        raise PipelineError("The SCF debt types no longer add up to DEBT; check the extract's variable list")

    def families(rows) -> bool:
        return rows["YY1"].nunique() >= ctx.min_records

    def quantiles(rows, col):
        return weighted_quantiles(rows[col], rows["w"]) if families(rows) else None

    def groups(rows, col):
        return _drop_none(by_groups(rows, dims, lambda r: quantiles(r, col), ctx.min_records))

    def holding(mask):
        rows = d.assign(_has=mask)
        return _drop_none(by_groups(rows, dims, lambda r: round_to(weighted_share(r["_has"], r["w"]), 4) if families(r) else None, ctx.min_records))

    types = {}
    for key, (label, cols) in TYPES.items():
        amount = sum(d[c] for c in cols)
        holders = d.assign(_amt=amount)[amount > 0]
        types[key] = {"label": label, "holding": holding(amount > 0), "groups": groups(holders, "_amt")}
    data = {
        "bands": SCF_BANDS,
        "networth": {"groups": groups(d, "NETWORTH")},
        "retirement": {"groups": groups(d, "RETQLIQ")},
        "debt": {
            "total": {"holding": holding(d["DEBT"] > 0), "groups": groups(d[d["DEBT"] > 0], "DEBT")},
            "types": types,
        },
    }
    ctx.write("us.fed.scf", data, year=year,
              note=f"Families by age of the head; {year} dollars. Retirement accounts are IRAs, Keoghs and account-type pensions "
                   "(all families, including those with none). Debt percentiles count only families that owe that kind of debt. "
                   "All five implicates pooled.")


def _drop_none(groups: dict) -> dict:
    return {k: v for k, v in groups.items() if v is not None}

"""Builders by source id (the ids in backend/data/sources.json). Sources without a builder are 'pending'."""

from . import acs_pums, births_538, bps, datagovmy_births, nhanes, opendosm, ssa_names, un_wpp, worldbank_pip, worldbank_wdi

BUILDERS = {
    "census_acs_pums": acs_pums,
    "nchs_nhanes": nhanes,
    "ssa_names": ssa_names,
    "births_538": births_538,
    "un_wpp": un_wpp,
    "worldbank_pip": worldbank_pip,
    "worldbank_wdi": worldbank_wdi,
    "opendosm": opendosm,
    "datagovmy_births": datagovmy_births,
    "bps": bps,
}

# un_wpp before worldbank_pip, which reads the UN population figures.
ORDER = ["census_acs_pums", "nchs_nhanes", "ssa_names", "births_538", "un_wpp", "worldbank_wdi", "worldbank_pip", "opendosm", "datagovmy_births", "bps"]

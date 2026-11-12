"""Builders by source id (the ids in backend/data/sources.json). Sources without a builder are 'pending'."""

from . import acs_pums, anthropic_aei, bea_rpp, births_538, bls_atus, bls_cpi, bls_oews, bls_projections, bps, census_ahs, cia_factbook, datagovmy_births, fed_scf, fhfa_hpi, nchs_nhis, nchs_nsfg, nhanes, oecd, opendosm, ssa_names, un_wpp, worldbank_pip, worldbank_wdi

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
    "bls_oews": bls_oews,
    "bls_projections": bls_projections,
    "bls_cpi": bls_cpi,
    "bea_rpp": bea_rpp,
    "fhfa_hpi": fhfa_hpi,
    "fed_scf": fed_scf,
    "census_ahs": census_ahs,
    "bls_atus": bls_atus,
    "nchs_nhis": nchs_nhis,
    "nchs_nsfg": nchs_nsfg,
    "anthropic_aei": anthropic_aei,
    "oecd": oecd,
    "cia_factbook": cia_factbook,
}

# un_wpp before worldbank_pip, which reads the UN population figures.
ORDER = ["census_acs_pums", "nchs_nhanes", "ssa_names", "births_538", "un_wpp", "worldbank_wdi", "worldbank_pip", "opendosm", "datagovmy_births", "bps", "bls_oews", "bls_projections", "bls_cpi", "bea_rpp", "fhfa_hpi", "fed_scf", "census_ahs", "bls_atus", "nchs_nhis", "nchs_nsfg", "anthropic_aei", "oecd", "cia_factbook"]

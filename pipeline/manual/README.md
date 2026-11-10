# Files you download by hand

Some publishers don't offer a stable download link, or their files are very large. Save those files
here, one folder per source id (the ids in `data/sources.json`), with the exact file names below.

| Folder | Files |
| --- | --- |
| `un_wpp/` | From https://population.un.org/wpp/downloads, CSV format: `WPP2024_Demographic_Indicators_Medium.csv.gz`, `WPP2024_PopulationBySingleAgeSex_Medium_2024-2100.csv.gz`, `WPP2024_Life_Table_Complete_Medium_Both_2024-2100.csv.gz`, `…_Female_2024-2100.csv.gz`, `…_Male_2024-2100.csv.gz` |
| `worldbank_pip/` | `pip_percentiles.csv`: the Poverty and Inequality Platform percentiles dataset from https://datacatalog.worldbank.org |
| `worldbank_wdi/` | Optional `license_overrides.json` (`{"INDICATOR.CODE": "why its license allows commercial use"}`) |
| `opendosm/` | Only if a download fails: `<catalogue id>.csv` from https://open.dosm.gov.my/data-catalogue/<id> |
| `datagovmy_births/` | Only if a download fails: `births.csv` from https://data.gov.my/data-catalogue/births |
| `bps/` | See `bps/README.md` |

Downloads the pipeline fetches itself are cached in `pipeline/raw/` (not committed).

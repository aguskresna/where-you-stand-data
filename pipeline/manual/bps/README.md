# BPS files

BPS (Statistics Indonesia) tables are copied by hand from bps.go.id. BPS allows commercial use as long
as each table is cited with its title, the date you accessed it and a direct link, and the app doesn't
suggest BPS endorses it.

| File | Builds | Columns |
| --- | --- | --- |
| `poverty_line.json` | `id.bps.poverty_line` | See the file: `value` (rupiah per person per month), `period`, `bands` as `[label, from multiple, to multiple]` with the last `to` null, and `citation`. Shipped with the March 2026 line. |
| `spending_brackets.csv` | `id.bps.spending` | `province` (`Indonesia` or a province name as in the app), `from`, `to` (rupiah per person per month; leave `to` empty for the top bracket), `share` (0–1), optional `period` |
| `wages_province_job.csv` | `id.bps.wages` | `province`, `job` (`all` for every job), `wage` (average monthly net wage, rupiah), optional `period` |
| `wages_age.csv` | `id.bps.wages` | `age_group` (`15-19`, `20-24`, …, `60+`), `wage` |
| `cpi_groups.csv` | `id.bps.cpi` | `code` (`overall` plus one row per group), `label`, `change` (12-month change, 0.027 = 2.7%), optional `weight` (0–1), `as_of` (`YYYY-MM`) |
| `citations.json` | — | `{"spending_brackets.csv": {"title": "…", "accessed": "YYYY-MM-DD", "url": "https://www.bps.go.id/…"}, …}` for every CSV |

The `*.example.csv` files show the layout with made-up numbers. Copy one to the real name only after
replacing every number with the BPS figures.

When BPS publishes a new poverty line (each March and September survey round), update `value`,
`period` and `citation` in `poverty_line.json`, then run `python -m statsapp_pipeline build bps`.

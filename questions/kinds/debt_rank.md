### `debt_rank`
Debt against households of the same age, from the Survey of Consumer Finances.
Implemented in `app/lib/calc/debt_rank.dart`.

`params`:
- `dataset`; `parts` (the age band, `"bands": "@SCF"`), `fallbackOrder`, `prefix`, `suffix`,
  `missing`, `phrases`.
- `amounts`: input keys summed into the total.
- `totalPath`: path to `{holding: {group: share}, groups: {group: [101 values]}}`: the total
  among households that owe anything (`["debt", "total"]`, or one type such as
  `["debt", "types", "education"]`).
- `typesPath` (optional): path to `{type: {label, holding, groups}}`; every amount input named
  after a type and above zero becomes a bar (its percentile among holders of that type), titled
  `barsTitle`. `missingType` is the error when a type has no figures (`{label}`).
- `format` for money; `whenZero`: the text for a total of zero (as in `group_rank`).

Values: `total`, `rank`, `pct`, `median`, `holding` (the share owing anything), `none`
(1 − holding), `group`, part phrases, `n.KEY`. Grid: rank, or the share with no debt when the
total is zero. Bars: percentile.

Questions: us-debt-check, us-student-debt.

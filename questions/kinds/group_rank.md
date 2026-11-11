### `group_rank`
Rank a value within quantiles for the person's group, falling back to broader groups when the
exact one has too few survey records. Implemented in `app/lib/calc/group_rank.dart`, with shared
helpers in `app/lib/engine/ranks_common.dart` and `app/lib/engine/ranks_expr.dart`.

`params`:
- `dataset`; `path` to an object of `{groupKey: [ascending thresholds]}`, or, without `parts`,
  straight to one list of thresholds (e.g. `["measures", "first_birth_age"]`).
- The person's value, one of:
  - `value`: an input key, or a JSON number for a constant (`1000000` for "worth $1 million");
  - `valueExpr`: an expression over input keys and numbers (see "Expressions" below), e.g.
    `"abs(you - partner)"`, `"rent / income * 100"`, `"a + b + c"`.
  - `requirePositive`: `{inputKey: error}`; the error is shown when that input isn't above zero.
  - `invalidValue`: the error when the value isn't a finite number (default "Check the numbers
    you entered.").
- `parts`: one per key segment, `{"input": KEY, "name": NAME (default the input key),
  "bands": "@SCF" | ["<20", "20-24", ...] (turns a number into a band), "round": true and
  "clamp": [lo, hi] (a whole number, e.g. a single year of age), "all": "*" (the token meaning
  everyone, e.g. "Malaysia" or "US"), "phrase": {value: text, "_": template, "*": text when
  generalised}}`. `_` may use `{label}`, `{lower}` (the label in lower case), `{band}`, `{value}`.
- `fallbackOrder` (indexes of parts to generalise first); `fallbackCaveat` (template; `""` for
  none; default "There are too few survey records for your exact group, so this compares you with
  {group}."); `missing` (the error when no group matches).
- `prefix`, `suffix`: words before and after the group phrase ("Americans", "in the US").
- `positions`: path to custom percentile positions such as OEWS's or HIES's `p`.
- `format` for the distribution's values (`median`, `p25`, `p75`, `next10`): `{"type": "money",
  "currency": "USD"}`, `{"type": "number", "digits": 0, "suffix": " minutes"}`, `{"type":
  "height"}` or `{"type": "percent"}` (a share 0-1). `valueFormat` for `{value}` (default `format`).
- `grid`: `"rank"` (default: the people below you, with "you") or `"above"` (the share above the
  value, as a share grid without "you").
- `shareAbove`: `[{"name": "over30", "at": 30}]` adds `{over30}`, the share of the group above 30.
- `fields`: `{NAME: {"path": [keys into the dataset]} | {"key": FIELD of the matched value},
  "format": spec}`, extra figures such as `{"sameAge": {"path": ["sameAge"], "format": {"type":
  "percent"}}}`. A missing figure shows as '–'.
- `alsoFor`: `[{"group": "*", "stat": [label, value]}]` adds a stat ranked in another group of the
  same object, with that group's `{pct}`, `{pctAbove}`, `{rank}`, `{median}`...; left out when
  that group is missing.
- `whenZero`: `{"headline", "sentence", "stats", "caveats"}` (each optional) replacing the
  question's text when the value is exactly 0 ("Same age").
- `phrases`: `{NAME: phrase}` extra values from phrases (see the README).

Values: `rank` ("72nd percentile", "Top 3%", "Below the 10th percentile"), `pct` ("72%"),
`pctAbove` (the share above the value, "28%"), `median`, `p25`, `p75`, `next10` (the value needed
for the next 10%, '–' from the 90th percentile up), `value`, `group` ("women aged 25–34 in
Texas"), each part's phrase by its name and its segment as `seg.NAME`, `n.KEY` (number inputs
formatted plainly), every `shareAbove` and `fields` name. Adds a caveat when it had to fall back.
Grid: rank, with "you", or the share above.

#### Expressions
`app/lib/engine/ranks_expr.dart`: numbers (`100`, `0.5`), input keys (read as numbers), `+ - * /`,
unary minus, brackets, and the functions `abs`, `min`, `max` (any number of arguments), `sqrt`,
`round`, `floor`, `ceil`. Nothing else: no comparisons, variables or strings. Division by zero
gives a value that isn't finite, which the kind turns into the `invalidValue` error.

Questions: us-income-rank, us-height-rank, us-commute-rank, us-work-hours-rank, my-income-rank,
us-net-worth, us-retirement-savings, us-millionaire-odds, us-pay-in-job, us-weight-rank,
us-waist-rank, us-sleep-rank, us-home-size, us-age-first-child, us-birth-weight-rank,
us-mother-age-rank, us-rent-burden, us-age-gap.

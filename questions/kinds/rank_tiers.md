### `rank_tiers`
Named tiers cut at percentiles of a distribution (Malaysia's B40/M40/T20) or at ratios to a
median after an equivalence scale (US middle income), plus the person's rank.
Implemented in `app/lib/calc/rank_tiers.dart`.

`params`:
- `dataset`; `path` to the distribution the person is ranked in (or to groups, with `parts`,
  `fallbackOrder`, `fallbackCaveat`, `prefix`, `suffix` as in `group_rank`); `positions`.
- `value` / `valueExpr`: the person's amount; `format` for amounts.
- `mode` `"percentile"` (default): tiers compare the person's percentile. `mode` `"ratio"`: tiers
  compare `value × scale ÷ median`, with `scale` an expression (`"sqrt(3 / size)"`) and
  `medianPath` the path to the median. The rank uses `value × scale` too.
- `tiers`: `[{"name", "below": bound | "upTo": bound, "range": template}]`, lowest first; the last
  has no bound. `below` is exclusive, `upTo` inclusive. A bound is a number or an expression
  (`"2/3"`).
- `subTiers`: names for equal slices of the percentile range (deciles `B1`..`T2`).
- `nextStat`: `[label, value]` added below the top tier, with `{next}` and `{toNext}`.

Values: `tier`, `sub`, `rank`, `pct`, `ratio` (2 decimals), `value`, `cut1`, `cut2`... (each
bound as an amount: the percentile's value, or bound × median ÷ scale in the person's own terms),
`range` (the tier's template, filled), `median` (ratio mode, in the person's terms), `group`, part
phrases, `n.KEY`. Grid: rank.

Questions: my-b40, us-middle-class.

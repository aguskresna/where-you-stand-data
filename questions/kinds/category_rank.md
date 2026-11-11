### `category_rank`
Rank among ordered categories, counting half of those in the person's category (`midRank`), or
among brackets of a continuous value spread evenly inside each bracket (`bracketRank`).
Implemented in `app/lib/calc/category_rank.dart`.

`params`:
- `dataset`; `path` to the groups (or, without `parts`, to one distribution); `parts`,
  `fallbackOrder`, `fallbackCaveat` (default none), `prefix`, `suffix`, `missing`, `phrases` as in
  `group_rank`.
- `mode` `"categories"` (default): groups hold `[share per category]`, lowest first; `index` is
  the input whose value (a number, or a select's "0".."4") picks the category, capped at the last
  one ("4+").
- `mode` `"brackets"`: groups hold `[[from, to|null, share], ...]`; the value comes from `value`
  or `valueExpr` as in `group_rank`; `format` for the bracket ends; `rangeText`: `{"closed":
  "{from} to {to}", "open": "{from} or more"}`.

Values: `rank`, `pct`, `pctAbove`, `group`, part phrases, `n.KEY`; categories add `same` (the share
in the person's category); brackets add `range`, `from`, `to`, `bracketShare`, `value`.
Grid: rank.

Questions: us-family-size, us-education-rank, id-spending-rank.

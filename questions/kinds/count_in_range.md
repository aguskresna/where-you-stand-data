### `count_in_range`
How many people of a group fall in an age range, and how many of them match, from counts by
single year of age. Implemented in `app/lib/calc/count_in_range.dart`.

`params`:
- `dataset`; `path` to the groups, `{key: {COUNT: [per age], TOTAL: [per age]}}`; `agesPath`
  (default `["ages"]`) to the `[first, last]` age; `range`: the range input; `countField`,
  `totalField` (e.g. `"single"`, `"all"`).
- `parts`, `fallbackOrder`, `fallbackCaveat` (default none), `prefix`, `suffix`, `phrases` as in
  `group_rank`. A group with a missing or suppressed (null) cell anywhere in the range counts as
  missing, so the lookup falls back (a state to the whole US).
- `missing`: the error when no group works; `empty`: the error when the range holds no one.

Values: `count`, `total` (compact, "1.2 million"), `share`, `lo`, `hi`, `group`, part phrases,
`n.KEY`. Grid: share.

Questions: us-singles-near-you.

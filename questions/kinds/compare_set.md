### `compare_set`
A value for each item in a set, sorted, as bars (or one stat per item), with the first and last
values for the sentence. Used by us-life-exp-state, world-life-exp-anywhere, us-salary-furthest,
world-salary-across, world-work-hours.

`params`:
- `dataset`; `items`: `{"input": multiKey}` or `{"keysOf": [path]}`, optional `"exclude": inputKey`.
- `value`: `{"path": [... "{item}" ...]}`, plus at most one of
  - `"series": {"first": ["first"], "last": ["last"]}`: the path holds an array indexed by
    year − first; the year is this year clamped to the data's range (value `{year}`);
  - `"scale": {"by": amountInput, "base": {"input": KEY, "fixed": {"*": 100}, "path": [...], "error"}}`:
    value × amount / base;
  - `"ppp": {"series": [path to {ISO3: {YYYY: rate}}], "home": KEY, "amount": KEY, "format", "error"}`
    (no `path`): amount / home rate × their rate at the latest year both have. Adds `{converted}`
    (amount at the home's latest rate) and `{homeYear}`.
- `labels` (label source, see item_record), `sort` (`desc`, `asc` or none), `mark` (input whose
  value is marked), `format` (item values; `"currencyOfItem": true` formats money in each item
  country's currency), `spreadFormat`, `empty` (error when no item has a value), `allowEmpty`.
- `extra`: `{name: code}`: values for items outside the set, such as `{"world": "WLD"}`.
- `you`: `{"label": "You", "product": [inputKeys], "format"}`: a marked bar for the person, sorted in
  with the rest. Values `{you}`, `{fewer}` (items below it), `{total}` (items in the set).
- `shown`: `{name: {"input": KEY, "format"} | {"labelOf": KEY}}`: inputs formatted for the text.
- `phrases`: `{name: {"one": t, "many": t}}` chosen by the number of items, or any phrase.
- `bars`: `title`, `unit`, `currency`, `ends` (keep only the first and last n).
- `rowStats`: `{"label": "Same living standard in {label}"}`: one stat per item instead of bars.
- `stats` / `caveats`: conditional, as in item_record.

Values: `first`, `firstLabel`, `last`, `lastLabel`, `spread`, `count`, and those above.

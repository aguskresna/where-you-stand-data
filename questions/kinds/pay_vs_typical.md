### `pay_vs_typical`
Your pay as a multiple of the median or average pay of your group, from wage tables that give one
figure per group. Used by my-pay-median and id-pay-average.

`params`:
- `dataset`; `amount` (money input); `currency`; `phrases` (`{name: phrase}`, e.g. `who`).
- `main`: `{"table": [path], "keys": [templates tried in order], "field": "median" | null (the entry
  is the number itself), "parts": [names for the matched key's '|' parts], "partPhrases": {part:
  {value: text, "_": "in {value} "}}, "fields": {name: field} (more money figures from the record),
  "label": bar label template}`.
- `others`: `[{"table", "key", "field", "label", "band": {"input": KEY, "part": 0, "exclude": [...]}}]`:
  more groups; `band` turns a number input into the band among the table's keys. Groups the data
  doesn't have are left out.
- `barsTitle`; `fallbackCaveat` (added when a later key was used); `error`.

Values: `ratio` ("2.1×"), `ratioNum` ("2.1"), `typical`, each part name and `<part>Phrase`, the
`fields` names and the `phrases`. Bars (ratio): the main group, then each other group; labels are
capitalised.

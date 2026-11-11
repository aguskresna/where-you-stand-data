### `item_record`
Look up records for chosen items and show their fields, ratios between fields, a grid and bars.
Used by us-pay-gap-job, us-job-outlook, us-ai-exposure, us-degree-earns, us-language-community,
us-diaspora, us-risk-odds, us-couple-match, us-family-then-now, world-ai-use, world-religion,
my-pay-gap, my-education-earns.

`params`:
- `dataset`; `error` (message when a required item is missing; may use `{in.KEY}`).
- `items`: `{name: {"path": [keys], "optional": true, "pick": "maxKey", "nonEmpty": field, "error": text}}`.
  Each path element is a template (`"{occupation}"`, `"{state}|female"`) or a phrase
  (`{"input": "sex", "map": {"M": "{edu}|{partnerEdu}"}, "default": "{partnerEdu}|{edu}"}`), so a
  key can depend on several inputs. `[]` is the whole dataset. `pick: "maxKey"` takes the record
  under the largest numeric key of the object at `path` (the latest year). `nonEmpty` refuses a
  record whose list field is empty.
- `values`: `{name: spec}`, computed in order. Sources: `"field": "item.field.sub"` (or `"item"` for
  a record that is itself a number); `"ratio": [ref, ref]`; `"text": phrase`; `"key": item` (the key
  the item was found under); `"top": "item.listField", "take": 0|1` (from the `[label, value]` row
  with the largest value). Then `map` (raw value to text), `orElse` (number when missing), `scale`,
  `abs`, `format`, and `atLeast` with `then` / `else` templates (`{value}` is the formatted value,
  `{inverse}` the formatted 1/value), e.g. "The first is {value} times as likely".
- `grid`: `{"share": valueName}` or `{"rank": valueName}`, optional `caption`.
- `bars`: `title` (template), `unit`, `currency`, `scale`, `limit`, `labels` (label source), and one of
  - `"list": "item.field"`: rows `[code or label, value]`, optional `"sort": "desc"`;
  - `"items": [[label template, valueName], ...]`;
  - `"each": {"codes": [path to a list of codes], "value": [path with {code}], "mark": inputKey}`;
  - `"rank": {"path": [...], "by": field, "label": field, "top": 5, "mark": itemName}`: the top
    records, plus the marked one when it's outside the top.
- `stats`: extra `[label, template, valueName]`, shown only when that value exists; `caveats`: strings
  or `{"text", "if": valueName, "above": n, "below": n}`.

Format specs (shared by the record kinds): `{"type": "money", "currency": "USD"}` (or
`"currencyFor": countryInput`, `"currencyOf": moneyInput`), `pct` / `change` (`digits`), `compact`,
`int`, `num` (`digits`, default 1), `years`, `oneIn`, `times`, `ordinal`, `height`, `text`
(`"case": "lower"`); any may add `prefix` / `suffix`. Without a format, numbers print plainly (2024).

Label sources: `"@listName"` (a modes.json list), an input key (its options), or
`{"dataset", "path", "field"}` (an object of code: label or code: {field}).

Values: the names in `values`, plus every input as `{KEY}`, `{in.KEY}` and `{label.KEY}`.

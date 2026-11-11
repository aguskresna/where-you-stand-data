### `group_share`
A share for the person's group (married by an age, own their home, still married after 10 years),
falling back to broader groups. Implemented in `app/lib/calc/group_share.dart`.

`params`:
- `dataset`; `parts` as in `group_rank` (each part has a `name`; two parts may read the same
  input, e.g. `age` as a whole number and `band` as an age band).
- Either `path` + `fallbackOrder` (one lookup over all parts), or `lookups`: an ordered list of
  `{"path", "key": [part names], "fallbackOrder", "exact": true (only an exact match counts),
  "skipIf": {inputKey: value}, "missCaveat": template}`. The first lookup that matches is used;
  each one tried and missed adds its `missCaveat`. An empty `fallbackOrder` means no fallback.
- `field`: the share's field when groups hold objects (`"y10"` in `{y10, y20}`); groups without it
  count as missing. `fields`: extra values as in `group_rank` (`{"key": "y20"}` reads the hit).
- `then`: `{"path", "yearPath", "fallbackOrder" (default the lookup's), "stat": [label, value]}`
  looks up the same key in an earlier year's groups and adds the stat with `{then}` and
  `{thenYear}`; left out when there is no such data.
- `crossing`: `{"path", "key": [part names, "#" for the step], "from", "to", "at": 0.5, "name":
  "half", "found": "age {age}", "none": "not by 80"}`: the first step where the series reaches
  `at`, interpolated linearly from the step before.
- `prefix`, `suffix`, `fallbackCaveat` (default none), `missing`, `phrases`.

Values: `share`, `shareNot` (1 − share), `group`, each part's phrase by its name (the matched
segment for parts in the key used, the person's own otherwise) and `seg.NAME`, `n.KEY`, `fields`,
the crossing's name. Grid: share.

Questions: us-marriage-timing, us-own-home-age, us-living-with-parents, us-will-it-last.

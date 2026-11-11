### `name_popularity`
Babies given a name in a year, its rank, peak and total. Used by us-name-popularity.

`params`: `dataset` (sharded by the first two lowercase letters a-z of the name; the kind computes
the shard from the name input, so no `shard` param), `totals` (babies by sex and year), `name`,
`sex`, `year` (input keys), `kids` (phrase), `notFound` (error template), and `phrases`:
`{name: {"listed": template, "unlisted": template}}`, chosen by whether the name is listed in that
year.

Values: `name` (letters only, first capital), `kids`, `year`, `rank`, `count`, `oneIn` (listed
only), `peakYear`, `peakCount`, `total`, `since` (first year in the totals), `lastYear`,
`lastCount`, and the `phrases`.

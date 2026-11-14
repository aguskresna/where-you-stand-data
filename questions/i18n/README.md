# Catalog translations

- `ms.json`, `id.json`: the catalog's text in Malay and Indonesian, laid over the English catalog
  by the app (format: `../README.md`, "Translations").
- `translations.csv`: the same text as a sheet for a translator or native speaker, one row per
  English text, in the columns of the shared translation workflow. Re-generate it after any
  change to the English or the overlays:
  `.venv/Scripts/python -m statsapp_pipeline sheet` (from `pipeline/`).
- A returned sheet is checked, then written into `ms.json` / `id.json`, with
  `.venv/Scripts/python -m statsapp_pipeline sheet-import <returned.csv> [--write]`.

The steps for a review, and the prompt to send with this sheet and the app's own sheet, are in
`app/docs/TRANSLATIONS.md` ("Native-speaker review") in the app repository.

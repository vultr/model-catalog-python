# AGENTS.md - vultr/model-catalog-python

`vultr-model-catalog` (`vultr_model_catalog`): fetches `GET /v1/models` from
Vultr Inference and turns each Model Document 2.4 entry into a flat
`CatalogModel`. The Hermes integration builds on this; none of its code lives
here.

Human overview: `README.md`. Field mapping, tolerance and cache format:
`docs/catalog.md`.

## What holds the design up

- **The twin.** `vultr/model-catalog-typescript` is the same library for
  TypeScript (Pi, OpenClaw, OpenCode). Same input, same output.
  `fixtures/*.normalized.json` is the contract: the TypeScript repo generates
  it, `tests/test_model.py` must match it. Never edit those files by hand
  here. A change to normalization is a change to both repos, in the same turn
- **The schema is not ours.** The input is OpenRouter's provider Model
  Document, schema 2.4; the `reasoning` block follows OpenRouter's
  `ModelReasoning`. The `fixtures/` payloads are the reference shape. Read
  those, not web summaries, before changing the mapping
- **Harness-neutral.** No Hermes imports, names or units in this repo. A
  harness wants a different shape: that is a mapper in the harness package
- **No runtime dependencies.** `dependencies` stays empty; stdlib only.
  A plugin runs inside the harness's interpreter, so the floor is Python
  3.11, not this machine's default
- **Nothing is guessed.** A value the document does not carry is `None`.
  No default context window, no assumed price
- **One bad entry never fails the catalog.** `parse_catalog` skips it and
  reports an issue. `load_catalog` raises `CatalogError` only when there is
  neither a network payload nor a cache to serve
- **Prices are strings.** `cost_usd` stays an exact decimal string. Convert
  with `usd_per_million`, which goes through `Decimal`. Do not multiply
  floats: `0.0000001 * 1e6` is `0.09999999999999999`

## Working here

- `uv run pytest -q` must pass, and on the floor too:
  `uv run --python 3.11 --isolated pytest -q`
- After a normalization change lands in the TypeScript repo, copy its
  `fixtures/*.json` here and run the tests
- The cache file format is shared with the TypeScript library. Changing it
  is a change to both
- `__init__.py` is the public contract: import the names, list them in
  `__all__`. A new export is deliberate; add it to the README surface list
- Nothing mutable at module level. Models are frozen dataclasses
- Network access goes through the `Transport` callable so tests never touch
  the network
- Put lasting explanation in `docs/`, not in the source. If a comment is
  needed, make it short. Docs describe current behavior, not history
- Write commit messages to the Conventional Commits spec
- No em dashes or en dashes anywhere: prose, comments, commit messages and
  docs use plain hyphens, `·`, or `:`
- No AI trailers on commits (`Co-Authored-By`, `Generated with`, ...)
- Never force-push; never rewrite pushed history

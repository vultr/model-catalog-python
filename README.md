# vultr-model-catalog

Fetch `GET /v1/models` from Vultr Inference and turn each Model Document 2.4
entry into a flat `CatalogModel`. This is the base the Python harness
integrations (Hermes) build on. The TypeScript twin is
`model-catalog-typescript`; both produce the same output for the same input.

## Install

```bash
pip install vultr-model-catalog
```

No runtime dependencies. Python 3.11+.

```python
from vultr_model_catalog import load_catalog

catalog = load_catalog(cache_path="~/.cache/vultr/catalog.json", max_age=300)
for model in catalog.chat_models:
    print(model.id, model.context_window, model.price_per_million()["prompt"])
```

## Surface

- `load_catalog(...)`: fetch, normalize, fall back to the last good payload
  when the network fails. `catalog.source` is `network`, `cache` or
  `stale-cache`. Raises `CatalogError` only when there is nothing to serve.
  `catalog.chat_models` and `catalog.agent_models` filter by `is_chat` and
  `is_agent`
- `fetch_catalog(...)`: the raw JSON payload. The catalog is public;
  `api_key` is optional. `user_agent` puts the caller's product token ahead
  of the library's own `User-Agent` (`docs/catalog.md`, Request)
- `parse_catalog(payload)`: documents plus `issues`. A bad entry is skipped
  and reported, it never fails the catalog
- `normalize_model(document)`: one `CatalogModel`
- `usd_per_million(cost_usd)`: exact conversion of a per-token price string
- `model.output_of(type)`, `model.input_of(type)`: one modality of `outputs` /
  `inputs`, or `None`
- `load_media_catalog(...)`: the per-surface catalogs (image, video, music,
  voices, tiers, price options, limits and alignment languages), one
  `ModelMedia` per model, its alignment an `AlignmentRecord`;
  `fetch_media_payloads`, `build_media_catalog`, `speech_model_ids` and
  `MEDIA_SOURCES` are its parts (`docs/catalog.md`, Media catalog)

`CatalogModel` carries `context_window`, `max_output_tokens`,
`input_modalities`, `output_modalities`, `pricing` (exact USD per token
strings), `tools`, `structured_outputs`, `streaming`, `supported_parameters`,
`parameters`, `reasoning`, `is_ready`, `deprecation_date`, and every modality
as `outputs` and `inputs`. `model.is_chat` is
true when the model outputs text; rerankers, embedders, image generators,
transcription and decision models are in the catalog too. `model.is_agent` is
true for the chat models a coding harness can drive: ready, with tool calling
and a known context window. A safety classifier outputs text but calls no
tools, so it is a chat model and not an agent model.

See `docs/catalog.md` for the field mapping and the cache format.

## Development

```bash
uv run pytest -q
```

`fixtures/` is shared with the TypeScript project. `*.normalized.json` is
generated there (`UPDATE_FIXTURES=1 npm test`) and copied here, so the two
libraries cannot drift apart without a test failing.

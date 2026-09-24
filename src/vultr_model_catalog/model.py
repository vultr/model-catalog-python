import math
from dataclasses import asdict, dataclass, field
from typing import Any

from .parse import ModelDocument
from .price import usd_per_million


@dataclass(frozen=True, slots=True)
class ModelPricing:
    """Exact decimal strings, USD per token (request: USD per request). None when unpriced."""

    prompt: str | None = None
    cached_prompt: str | None = None
    cache_write: str | None = None
    completion: str | None = None
    internal_reasoning: str | None = None
    request: str | None = None


@dataclass(frozen=True, slots=True)
class ReasoningSupport:
    mandatory: bool
    default_effort: str | None
    default_enabled: bool | None
    # Descending order. None means the model has no effort allowlist.
    supported_efforts: list[str] | None
    supports_max_tokens: bool


@dataclass(frozen=True, slots=True)
class CatalogModel:
    id: str
    name: str
    description: str | None
    created: int | None
    hugging_face_id: str | None
    quantization: str | None
    context_window: int | None
    max_prompt_tokens: int | None
    max_output_tokens: int | None
    input_modalities: list[str]
    output_modalities: list[str]
    pricing: ModelPricing
    tools: bool
    structured_outputs: bool
    streaming: bool
    supported_parameters: list[str]
    reasoning: ReasoningSupport | None
    is_ready: bool
    deprecation_date: str | None
    parameters: dict[str, Any] = field(default_factory=dict, compare=False)

    @property
    def is_chat(self) -> bool:
        """A chat model produces text. Rerankers, embedders and image generators do not."""
        return "text" in self.output_modalities

    def accepts_input(self, modality: str) -> bool:
        return modality in self.input_modalities

    def price_per_million(self) -> dict[str, float | None]:
        """USD per million tokens, the unit every harness model picker wants."""
        prices = asdict(self.pricing)
        del prices["request"]
        return {key: None if value is None else usd_per_million(value) for key, value in prices.items()}

    def to_dict(self) -> dict[str, Any]:
        """Language-neutral form. The TypeScript library emits the same document from
        toCanonical(); fixtures/*.normalized.json pins both."""
        document = asdict(self)
        del document["parameters"]
        return document


def _limit(value: Any) -> int | None:
    number = value.get("value") if isinstance(value, dict) else None
    if isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number):
        return None
    return int(number) if number == int(number) else None


def _is_windowed(entry: dict[str, Any]) -> bool:
    return any(key in entry for key in ("utc_start", "utc_end", "utc_days"))


def _price(entries: Any, kind: str, unit: str) -> str | None:
    """The base rate is the entry without a UTC window; windowed entries are time-of-day discounts."""
    matches = [
        entry
        for entry in entries or []
        if isinstance(entry, dict)
        and entry.get("type") == kind
        and entry.get("unit") == unit
        and isinstance(entry.get("cost_usd"), str)
    ]
    base = next((entry for entry in matches if not _is_windowed(entry)), matches[0] if matches else None)
    return base["cost_usd"] if base else None


def _modality(modalities: list[dict[str, Any]], kind: str) -> dict[str, Any]:
    return next((modality for modality in modalities if modality["type"] == kind), {})


def normalize_model(document: ModelDocument) -> CatalogModel:
    text_in = _modality(document["input_modalities"], "text")
    text_out = _modality(document["output_modalities"], "text")
    supported_inputs = text_in.get("supported_inputs") or {}
    parameters = text_out.get("supported_parameters") or {}
    reasoning = document.get("reasoning")

    return CatalogModel(
        id=document["id"],
        name=document.get("name") or document["id"],
        description=document.get("description"),
        created=document.get("created"),
        hugging_face_id=document.get("hugging_face_id"),
        quantization=document.get("quantization"),
        context_window=_limit(supported_inputs.get("max_context_length")),
        max_prompt_tokens=_limit(supported_inputs.get("max_prompt_length")),
        max_output_tokens=_limit(text_out.get("max_length")),
        input_modalities=[modality["type"] for modality in document["input_modalities"]],
        output_modalities=[modality["type"] for modality in document["output_modalities"]],
        pricing=ModelPricing(
            prompt=_price(text_in.get("pricing"), "prompt", "token"),
            cached_prompt=_price(text_in.get("pricing"), "cached_prompt", "token"),
            cache_write=_price(text_in.get("pricing"), "cache_write", "token"),
            completion=_price(text_out.get("pricing"), "completion", "token"),
            internal_reasoning=_price(text_out.get("pricing"), "internal_reasoning", "token"),
            request=_price(document.get("pricing"), "request", "request"),
        ),
        tools="tools" in parameters,
        structured_outputs="response_format" in parameters or "structured_outputs" in parameters,
        streaming=text_out.get("streaming") is True,
        supported_parameters=list(parameters),
        reasoning=ReasoningSupport(
            mandatory=reasoning.get("mandatory") is True,
            default_effort=reasoning.get("default_effort"),
            default_enabled=reasoning.get("default_enabled"),
            supported_efforts=reasoning.get("supported_efforts"),
            supports_max_tokens=reasoning.get("supports_max_tokens") is True,
        )
        if isinstance(reasoning, dict)
        else None,
        is_ready=document.get("is_ready") is not False,
        deprecation_date=document.get("deprecation_date"),
        parameters=parameters,
    )

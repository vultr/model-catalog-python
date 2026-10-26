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
class OutputSpec:
    """One output modality as the document states it: its parameters (supported, and the model's own as
    passthrough), prices and streaming. Media models live here: an image model's sizes, a speech model's voices."""

    type: str
    streaming: bool | None
    max_length: dict[str, Any] | None
    parameters: dict[str, Any]
    passthrough_parameters: dict[str, Any]
    pricing: list[dict[str, Any]]


@dataclass(frozen=True, slots=True)
class InputSpec:
    """One input modality: what a request may carry of that type (supported_inputs as stated) and its prices."""

    type: str
    supported_inputs: dict[str, Any]
    pricing: list[dict[str, Any]]


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
    # Every modality, in the document's order
    outputs: list[OutputSpec] = field(default_factory=list)
    inputs: list[InputSpec] = field(default_factory=list)

    @property
    def is_chat(self) -> bool:
        """A chat model produces text. Rerankers, embedders and image generators do not."""
        return "text" in self.output_modalities

    @property
    def is_agent(self) -> bool:
        """A chat model a coding harness can drive: ready, calls tools, states its context window."""
        return self.is_chat and self.is_ready and self.tools and self.context_window is not None

    def accepts_input(self, modality: str) -> bool:
        return modality in self.input_modalities

    def output_of(self, modality: str) -> OutputSpec | None:
        """The output of a type, or None when the model makes none."""
        return next((output for output in self.outputs if output.type == modality), None)

    def input_of(self, modality: str) -> InputSpec | None:
        """The input of a type, or None when the model reads none."""
        return next((item for item in self.inputs if item.type == modality), None)

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


def _is_number(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def _descriptors(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _entries(value: Any) -> list[dict[str, Any]]:
    return [entry for entry in value if isinstance(entry, dict)] if isinstance(value, list) else []


def _output_spec(modality: dict[str, Any]) -> OutputSpec:
    max_length = modality.get("max_length")
    streaming = modality.get("streaming")
    return OutputSpec(
        type=modality["type"],
        streaming=streaming if isinstance(streaming, bool) else None,
        max_length=max_length if isinstance(max_length, dict) and _is_number(max_length.get("value")) else None,
        parameters=_descriptors(modality.get("supported_parameters")),
        passthrough_parameters=_descriptors(modality.get("passthrough_parameters")),
        pricing=_entries(modality.get("pricing")),
    )


def _input_spec(modality: dict[str, Any]) -> InputSpec:
    return InputSpec(
        type=modality["type"],
        supported_inputs=_descriptors(modality.get("supported_inputs")),
        pricing=_entries(modality.get("pricing")),
    )


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


def _effort_values(descriptor: Any) -> tuple[bool, list[str] | None]:
    """(known, efforts): known is False when the descriptor does not say; efforts is None when any effort is accepted."""
    if not isinstance(descriptor, dict):
        return False, None
    if descriptor.get("type") == "unknown":
        return True, None
    values = descriptor.get("values")
    if descriptor.get("type") == "enum" and isinstance(values, list):
        return True, [value for value in values if isinstance(value, str)]
    return False, None


def _reasoning_support(parameters: dict[str, Any], root: Any) -> ReasoningSupport | None:
    """The text output's supported_parameters carry the facts: reasoning_effort (enum, or unknown when
    unrestricted) and reasoning (object whose properties hold effort, and max_tokens only when the budget
    is enforced). The root reasoning object is a temporary extension that will go away, so it only answers
    what the parameters do not: mandatory, the defaults, and any model whose parameters name no reasoning."""
    effort = parameters.get("reasoning_effort")
    reasoning = parameters.get("reasoning")
    fallback = root if isinstance(root, dict) else None
    if not isinstance(effort, dict) and not isinstance(reasoning, dict) and fallback is None:
        return None
    fallback = fallback or {}

    properties = reasoning.get("properties") if isinstance(reasoning, dict) else None
    properties = properties if isinstance(properties, dict) else None
    known, efforts = _effort_values(effort)
    if not known:
        known, efforts = _effort_values(properties.get("effort") if properties is not None else None)

    return ReasoningSupport(
        mandatory=fallback.get("mandatory") is True,
        default_effort=fallback.get("default_effort"),
        default_enabled=fallback.get("default_enabled"),
        supported_efforts=efforts if known else fallback.get("supported_efforts"),
        supports_max_tokens=("max_tokens" in properties)
        if properties is not None
        else fallback.get("supports_max_tokens") is True,
    )


def normalize_model(document: ModelDocument) -> CatalogModel:
    text_in = _modality(document["input_modalities"], "text")
    text_out = _modality(document["output_modalities"], "text")
    supported_inputs = text_in.get("supported_inputs") or {}
    parameters = text_out.get("supported_parameters") or {}

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
        reasoning=_reasoning_support(parameters, document.get("reasoning")),
        is_ready=document.get("is_ready") is not False,
        deprecation_date=document.get("deprecation_date"),
        parameters=parameters,
        outputs=[_output_spec(modality) for modality in document["output_modalities"]],
        inputs=[_input_spec(modality) for modality in document["input_modalities"]],
    )

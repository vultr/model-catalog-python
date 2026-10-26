"""Fetch and normalize a Model Document 2.4 catalog (Vultr Inference /v1/models)."""

from .catalog import (
    DEFAULT_BASE_URL,
    DEFAULT_TIMEOUT,
    Catalog,
    CatalogError,
    CatalogSource,
    Transport,
    build_catalog,
    fetch_catalog,
    load_catalog,
    models_url,
)
from .media import (
    MEDIA_SOURCES,
    MediaCatalog,
    MediaIssue,
    ModelMedia,
    SpeechRecord,
    build_media_catalog,
    fetch_media_payloads,
    load_media_catalog,
    speech_model_ids,
)
from .model import CatalogModel, InputSpec, ModelPricing, OutputSpec, ReasoningSupport, normalize_model
from .parse import SCHEMA_VERSION, CatalogIssue, ModelDocument, ParsedCatalog, parse_catalog
from .price import usd_per_million

__all__ = [
    "DEFAULT_BASE_URL",
    "DEFAULT_TIMEOUT",
    "MEDIA_SOURCES",
    "SCHEMA_VERSION",
    "Catalog",
    "CatalogError",
    "CatalogIssue",
    "CatalogModel",
    "CatalogSource",
    "InputSpec",
    "MediaCatalog",
    "MediaIssue",
    "ModelDocument",
    "ModelMedia",
    "ModelPricing",
    "OutputSpec",
    "ParsedCatalog",
    "ReasoningSupport",
    "SpeechRecord",
    "Transport",
    "build_catalog",
    "build_media_catalog",
    "fetch_catalog",
    "fetch_media_payloads",
    "load_catalog",
    "load_media_catalog",
    "models_url",
    "normalize_model",
    "parse_catalog",
    "speech_model_ids",
    "usd_per_million",
]

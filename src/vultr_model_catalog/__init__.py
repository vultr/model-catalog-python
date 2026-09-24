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
from .model import CatalogModel, ModelPricing, ReasoningSupport, normalize_model
from .parse import SCHEMA_VERSION, CatalogIssue, ModelDocument, ParsedCatalog, parse_catalog
from .price import usd_per_million

__all__ = [
    "DEFAULT_BASE_URL",
    "DEFAULT_TIMEOUT",
    "SCHEMA_VERSION",
    "Catalog",
    "CatalogError",
    "CatalogIssue",
    "CatalogModel",
    "CatalogSource",
    "ModelDocument",
    "ModelPricing",
    "ParsedCatalog",
    "ReasoningSupport",
    "Transport",
    "build_catalog",
    "fetch_catalog",
    "load_catalog",
    "models_url",
    "normalize_model",
    "parse_catalog",
    "usd_per_million",
]

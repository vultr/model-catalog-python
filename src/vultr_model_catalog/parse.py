import json
from dataclasses import dataclass
from typing import Any

SCHEMA_VERSION = "2.4"

# A Model Document 2.4 entry as served by GET /v1/models. Shape reference:
# the payloads in fixtures/
ModelDocument = dict[str, Any]


@dataclass(frozen=True, slots=True)
class CatalogIssue:
    index: int
    id: str | None
    message: str


@dataclass(frozen=True, slots=True)
class ParsedCatalog:
    documents: list[ModelDocument]
    issues: list[CatalogIssue]


def _is_modality_list(value: Any) -> bool:
    return isinstance(value, list) and all(
        isinstance(item, dict) and isinstance(item.get("type"), str) for item in value
    )


def parse_catalog(payload: Any) -> ParsedCatalog:
    """Accept the /v1/models envelope ({"data": [...]}) or a bare list.

    A bad entry is skipped and reported; it never fails the whole catalog.
    """
    entries = payload if isinstance(payload, list) else payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        raise TypeError("catalog payload must be a list or a dict with a data list")

    documents: list[ModelDocument] = []
    issues: list[CatalogIssue] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            issues.append(CatalogIssue(index, None, "entry is not an object"))
            continue
        model_id = entry.get("id")
        if not isinstance(model_id, str) or model_id == "":
            issues.append(CatalogIssue(index, None, "entry has no id"))
            continue
        if not _is_modality_list(entry.get("input_modalities")) or not _is_modality_list(
            entry.get("output_modalities")
        ):
            issues.append(CatalogIssue(index, model_id, "entry has no usable input_modalities/output_modalities"))
            continue
        if entry.get("schema_version") != SCHEMA_VERSION:
            issues.append(
                CatalogIssue(
                    index,
                    model_id,
                    f"schema_version is {json.dumps(entry.get('schema_version'))}, "
                    f'expected "{SCHEMA_VERSION}"; parsed anyway',
                )
            )
        documents.append(entry)
    return ParsedCatalog(documents, issues)

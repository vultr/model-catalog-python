"""The per-surface catalogs Vultr Inference publishes beside /v1/models, read into one record per model.

Each record is the surface's own entry, as served: these shapes are Vultr's and carry what the provider
document's closed schema cannot (size tables, modes, rules, voices). docs/catalog.md has the sources.
"""

import json
import os
import time
import urllib.parse
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any

from .catalog import DEFAULT_BASE_URL, DEFAULT_TIMEOUT, CatalogError, CatalogSource, Transport, get_json

MEDIA_SOURCES = ("public", "image", "video", "music")

_PATHS = MappingProxyType({
    "public": "/models?format=openrouter&output_modalities=all",
    "image": "/images/models",
    "video": "/videos/models",
    "music": "/music/models",
})


@dataclass(frozen=True, slots=True)
class MediaIssue:
    source: str
    message: str


@dataclass(frozen=True, slots=True)
class SpeechRecord:
    """A speech model's voices and the languages its card names (GET /v1/audio/voices?model=)."""

    voices: list[dict[str, Any]]
    languages: list[str]


@dataclass(frozen=True, slots=True)
class ModelMedia:
    id: str
    image: dict[str, Any] | None
    video: dict[str, Any] | None
    music: dict[str, Any] | None
    speech: SpeechRecord | None
    # By output modality, from the public shape (GET /v1/models?format=openrouter)
    quality_tiers: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    price_options: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    rate_limits: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Language-neutral form. The TypeScript library emits the same from toCanonicalMedia();
        fixtures/media.normalized.json pins both."""
        return asdict(self)


@dataclass(frozen=True, slots=True)
class MediaCatalog:
    models: list[ModelMedia]
    issues: list[MediaIssue]
    source: CatalogSource
    # Epoch milliseconds of the network fetch that produced these payloads.
    fetched_at: int


def _listed(payload: Any, source: str, issues: list[MediaIssue]) -> dict[str, dict[str, Any]]:
    """The entries of a {data: [...]} list with a string id, by id; the rest are issues."""
    by_id: dict[str, dict[str, Any]] = {}
    if payload is None:
        return by_id
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        issues.append(MediaIssue(source, "payload has no data list"))
        return by_id
    for index, entry in enumerate(data):
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str) or entry["id"] == "":
            issues.append(MediaIssue(source, f"entry {index} has no id"))
            continue
        by_id[entry["id"]] = entry
    return by_id


def _keyed_lists(value: Any) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(value, dict):
        return {}
    return {kind: [item for item in items if isinstance(item, dict)] for kind, items in value.items() if isinstance(items, list)}


def _speech_record(payload: Any, source: str, issues: list[MediaIssue]) -> SpeechRecord | None:
    if payload is None:
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        issues.append(MediaIssue(source, "payload has no data list"))
        return None
    voices = [voice for voice in payload["data"] if isinstance(voice, dict) and isinstance(voice.get("id"), str)]
    languages = payload.get("languages")
    return SpeechRecord(voices, [language for language in languages if isinstance(language, str)] if isinstance(languages, list) else [])


def speech_model_ids(public_payload: Any) -> list[str]:
    """The speech models the public shape names: those with a voice list."""
    data = public_payload.get("data") if isinstance(public_payload, dict) else None
    return sorted(
        entry["id"]
        for entry in (data if isinstance(data, list) else [])
        if isinstance(entry, dict) and isinstance(entry.get("id"), str) and isinstance(entry.get("supported_voices"), list)
    )


def build_media_catalog(payloads: Mapping[str, Any], source: CatalogSource, fetched_at: int) -> MediaCatalog:
    """One record per model any payload names, sorted by id. A missing payload gives nothing; a malformed
    one is an issue, and the others still answer."""
    issues: list[MediaIssue] = []
    public = _listed(payloads.get("public"), "public", issues)
    images = _listed(payloads.get("image"), "image", issues)
    videos = _listed(payloads.get("video"), "video", issues)
    music = _listed(payloads.get("music"), "music", issues)
    speech: dict[str, SpeechRecord] = {}
    for model_id, payload in (payloads.get("voices") or {}).items():
        record = _speech_record(payload, f"voices:{model_id}", issues)
        if record is not None:
            speech[model_id] = record

    ids = set(images) | set(videos) | set(music) | set(speech)
    for model_id, entry in public.items():
        if any(isinstance(entry.get(key), dict) and entry[key] for key in ("quality_tiers", "price_options", "rate_limits")):
            ids.add(model_id)

    models = []
    for model_id in sorted(ids):
        entry = public.get(model_id, {})
        rate_limits = entry.get("rate_limits")
        models.append(
            ModelMedia(
                id=model_id,
                image=images.get(model_id),
                video=videos.get(model_id),
                music=music.get(model_id),
                speech=speech.get(model_id),
                quality_tiers=_keyed_lists(entry.get("quality_tiers")),
                price_options=_keyed_lists(entry.get("price_options")),
                rate_limits={kind: limits for kind, limits in rate_limits.items() if isinstance(limits, dict)}
                if isinstance(rate_limits, dict)
                else {},
            )
        )
    return MediaCatalog(models, issues, source, fetched_at)


def fetch_media_payloads(
    *,
    base_url: str = DEFAULT_BASE_URL,
    api_key: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    headers: Mapping[str, str] | None = None,
    user_agent: str | None = None,
    transport: Transport | None = None,
) -> tuple[dict[str, Any], list[MediaIssue]]:
    """Read every source. Raise CatalogError only when every source failed; otherwise return the payloads
    and the failures, one MediaIssue per failed source."""
    base_url = base_url.rstrip("/")
    failed: list[MediaIssue] = []

    def read(source: str, path: str) -> Any:
        try:
            return get_json(
                base_url + path, api_key=api_key, timeout=timeout, headers=headers, user_agent=user_agent, transport=transport
            )
        except CatalogError as error:
            failed.append(MediaIssue(source, str(error)))
            return None

    payloads: dict[str, Any] = {source: read(source, _PATHS[source]) for source in MEDIA_SOURCES}
    speech_ids = [] if payloads["public"] is None else speech_model_ids(payloads["public"])
    voices = {model_id: read(f"voices:{model_id}", "/audio/voices?model=" + urllib.parse.quote(model_id, safe="")) for model_id in speech_ids}
    payloads["voices"] = {model_id: payload for model_id, payload in voices.items() if payload is not None}

    if len(failed) == len(MEDIA_SOURCES) + len(speech_ids):
        raise CatalogError("every media catalog failed: " + "; ".join(issue.message for issue in failed))
    return payloads, failed


def _read_cache(path: Path, base_url: str) -> dict[str, Any] | None:
    try:
        cached = json.loads(path.read_text(encoding="utf-8"))
        if cached["base_url"] != base_url or not isinstance(cached["fetched_at"], (int, float)) or not isinstance(cached["payloads"], dict):
            return None
        return cached
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _write_cache(path: Path, cache: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        temporary.write_text(json.dumps(cache), encoding="utf-8")
        temporary.replace(path)
    except OSError:
        # A read-only or missing cache directory must not fail a good fetch.
        pass


def load_media_catalog(
    *,
    base_url: str = DEFAULT_BASE_URL,
    api_key: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    headers: Mapping[str, str] | None = None,
    user_agent: str | None = None,
    transport: Transport | None = None,
    cache_path: str | os.PathLike[str] | None = None,
    max_age: float = 0,
    now: Callable[[], float] = time.time,
) -> MediaCatalog:
    """Fetch every surface catalog and the speech models' voices.

    A load where every source answered is the one cached (cache_path, a different file from
    load_catalog's). A load where some failed is served from that cache when there is one (stale), else
    as it is, with each failure in `issues`. A cache younger than max_age seconds is served without
    touching the network.
    """
    base_url = base_url.rstrip("/")
    path = Path(cache_path).expanduser() if cache_path is not None else None
    cached = _read_cache(path, base_url) if path else None
    now_ms = int(now() * 1000)

    if cached and now_ms - cached["fetched_at"] < max_age * 1000:
        return build_media_catalog(cached["payloads"], "cache", int(cached["fetched_at"]))

    try:
        payloads, failed = fetch_media_payloads(
            base_url=base_url, api_key=api_key, timeout=timeout, headers=headers, user_agent=user_agent, transport=transport
        )
    except CatalogError:
        if cached:
            return build_media_catalog(cached["payloads"], "stale-cache", int(cached["fetched_at"]))
        raise

    if failed and cached:
        stale = build_media_catalog(cached["payloads"], "stale-cache", int(cached["fetched_at"]))
        return MediaCatalog(stale.models, failed + stale.issues, stale.source, stale.fetched_at)

    catalog = build_media_catalog(payloads, "network", now_ms)
    if not failed and path:
        _write_cache(path, {"base_url": base_url, "fetched_at": now_ms, "payloads": payloads})
    return MediaCatalog(catalog.models, failed + catalog.issues, catalog.source, catalog.fetched_at)

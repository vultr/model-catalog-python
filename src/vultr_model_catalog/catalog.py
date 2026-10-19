import importlib.metadata
import json
import os
import platform
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from .model import CatalogModel, normalize_model
from .parse import CatalogIssue, parse_catalog

DEFAULT_BASE_URL = "https://api.vultrinference.com/v1"
DEFAULT_TIMEOUT = 8.0


def _user_agent() -> str:
    try:
        version = importlib.metadata.version("vultr-model-catalog")
    except importlib.metadata.PackageNotFoundError:
        version = "unknown"
    runtime = f"{platform.python_implementation()} {platform.python_version()}"
    system = " ".join(part for part in (sys.platform, platform.machine()) if part)
    return f"vultr-model-catalog/{version} (python; {runtime}; {system})"


USER_AGENT = _user_agent()

CatalogSource = Literal["network", "cache", "stale-cache"]

# (url, headers, timeout seconds) -> response body. Replaceable for tests and custom transports.
Transport = Callable[[str, Mapping[str, str], float], bytes]


class CatalogError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class Catalog:
    models: list[CatalogModel]
    issues: list[CatalogIssue]
    source: CatalogSource
    # Epoch milliseconds of the network fetch that produced this payload.
    fetched_at: int

    @property
    def chat_models(self) -> list[CatalogModel]:
        return [model for model in self.models if model.is_chat]

    @property
    def agent_models(self) -> list[CatalogModel]:
        return [model for model in self.models if model.is_agent]


def models_url(base_url: str = DEFAULT_BASE_URL) -> str:
    return base_url.rstrip("/") + "/models"


def _urlopen(url: str, headers: Mapping[str, str], timeout: float) -> bytes:
    request = urllib.request.Request(url, headers=dict(headers))
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def _merge_headers(*layers: Mapping[str, str]) -> dict[str, str]:
    # Header names are case-insensitive: a later layer replaces a name whatever its case.
    merged: dict[str, tuple[str, str]] = {}
    for layer in layers:
        for name, value in layer.items():
            merged[name.lower()] = (name, value)
    return dict(merged.values())


def fetch_catalog(
    *,
    base_url: str = DEFAULT_BASE_URL,
    api_key: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    headers: Mapping[str, str] | None = None,
    user_agent: str | None = None,
    transport: Transport | None = None,
) -> Any:
    """Return the raw JSON payload. Raise CatalogError on any transport or HTTP failure.

    The Vultr catalog is public; api_key is sent as a Bearer token when given.
    user_agent is the caller's product token, sent ahead of the library's own.
    """
    url = models_url(base_url)
    agent = f"{user_agent} {USER_AGENT}" if user_agent else USER_AGENT
    request_headers = _merge_headers(
        {"Accept": "application/json", "User-Agent": agent},
        headers or {},
        {"Authorization": f"Bearer {api_key}"} if api_key else {},
    )
    try:
        return json.loads((transport or _urlopen)(url, request_headers, timeout))
    except urllib.error.HTTPError as error:
        raise CatalogError(f"GET {url} returned HTTP {error.code}") from error
    except (OSError, ValueError) as error:
        raise CatalogError(f"GET {url} failed: {error}") from error


def build_catalog(payload: Any, source: CatalogSource, fetched_at: int) -> Catalog:
    parsed = parse_catalog(payload)
    return Catalog([normalize_model(document) for document in parsed.documents], parsed.issues, source, fetched_at)


def _read_cache(path: Path, base_url: str) -> dict[str, Any] | None:
    try:
        cached = json.loads(path.read_text(encoding="utf-8"))
        if cached["base_url"] != base_url or not isinstance(cached["fetched_at"], (int, float)):
            return None
        parse_catalog(cached["payload"])
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


def load_catalog(
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
) -> Catalog:
    """Fetch, normalize, and fall back to the last good payload when the network fails.

    cache_path keeps the last good payload. A cache younger than max_age seconds is
    served without touching the network; the default 0 always fetches. The cache file
    format is shared with the TypeScript library.
    """
    base_url = base_url.rstrip("/")
    path = Path(cache_path).expanduser() if cache_path is not None else None
    cached = _read_cache(path, base_url) if path else None
    now_ms = int(now() * 1000)

    if cached and now_ms - cached["fetched_at"] < max_age * 1000:
        return build_catalog(cached["payload"], "cache", int(cached["fetched_at"]))

    try:
        payload = fetch_catalog(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout,
            headers=headers,
            user_agent=user_agent,
            transport=transport,
        )
        catalog = build_catalog(payload, "network", now_ms)
    except (CatalogError, TypeError) as error:
        if cached:
            return build_catalog(cached["payload"], "stale-cache", int(cached["fetched_at"]))
        if isinstance(error, CatalogError):
            raise
        raise CatalogError(str(error)) from error

    if path and catalog.models:
        _write_cache(path, {"base_url": base_url, "fetched_at": now_ms, "payload": payload})
    return catalog

import json
import platform
import re
import sys
import tomllib
import urllib.error
from pathlib import Path

import pytest

from vultr_model_catalog import CatalogError, fetch_catalog, load_catalog, models_url
from vultr_model_catalog.catalog import USER_AGENT


class FakeTransport:
    def __init__(self, respond):
        self.respond = respond
        self.calls = []

    def __call__(self, url, headers, timeout):
        self.calls.append((url, dict(headers), timeout))
        return self.respond()


def down():
    raise OSError("network unreachable")


@pytest.fixture
def payload(load):
    return load("vultr-catalog.json")


@pytest.fixture
def ok(payload):
    return lambda: json.dumps(payload).encode()


@pytest.fixture
def cache_path(tmp_path):
    return tmp_path / "nested" / "catalog.json"


def test_models_url_tolerates_trailing_slashes():
    assert models_url() == "https://api.vultrinference.com/v1/models"
    assert models_url("http://localhost:8080/v1//") == "http://localhost:8080/v1/models"


def test_fetch_catalog_sends_no_credentials_unless_given_a_key(ok):
    anonymous = FakeTransport(ok)
    fetch_catalog(transport=anonymous)
    url, headers, timeout = anonymous.calls[0]
    assert url == "https://api.vultrinference.com/v1/models"
    assert "Authorization" not in headers
    assert timeout == 8.0

    keyed = FakeTransport(ok)
    fetch_catalog(transport=keyed, api_key="secret", base_url="https://example.test/v1/")
    assert keyed.calls[0][0] == "https://example.test/v1/models"
    assert keyed.calls[0][1]["Authorization"] == "Bearer secret"


def test_fetch_catalog_names_the_library_version_and_platform(ok):
    transport = FakeTransport(ok)
    fetch_catalog(transport=transport)
    agent = re.fullmatch(
        r"vultr-model-catalog/(?P<version>\S+) \(python; (?P<runtime>[^;]+); (?P<system>[^)]+)\)",
        transport.calls[0][1]["User-Agent"],
    )
    assert agent is not None
    pyproject = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text())
    assert agent["version"] == pyproject["project"]["version"]
    assert agent["runtime"] == f"{platform.python_implementation()} {platform.python_version()}"
    assert agent["system"].split()[0] == sys.platform


def test_fetch_and_load_catalog_put_the_callers_product_first(ok, cache_path):
    fetched = FakeTransport(ok)
    fetch_catalog(transport=fetched, user_agent="example-app/1.2")
    assert fetched.calls[0][1]["User-Agent"] == f"example-app/1.2 {USER_AGENT}"

    loaded = FakeTransport(ok)
    load_catalog(transport=loaded, cache_path=cache_path, user_agent="example-app/1.2")
    assert loaded.calls[0][1]["User-Agent"] == f"example-app/1.2 {USER_AGENT}"


def test_fetch_catalog_merges_headers_whatever_their_case(ok):
    transport = FakeTransport(ok)
    fetch_catalog(
        transport=transport,
        api_key="secret",
        user_agent="example-app/1.2",
        headers={"accept": "text/plain", "user-agent": "custom/1", "authorization": "Bearer other", "X-Extra": "1"},
    )
    headers = transport.calls[0][1]
    assert {name.lower(): value for name, value in headers.items()} == {
        "accept": "text/plain",
        "user-agent": "custom/1",
        "authorization": "Bearer secret",
        "x-extra": "1",
    }
    assert len(headers) == 4


def test_fetch_catalog_turns_http_transport_and_json_failures_into_catalog_error():
    def unavailable():
        raise urllib.error.HTTPError("https://x", 503, "Service Unavailable", {}, None)

    with pytest.raises(CatalogError, match="HTTP 503"):
        fetch_catalog(transport=FakeTransport(unavailable))
    with pytest.raises(CatalogError, match="network unreachable"):
        fetch_catalog(transport=FakeTransport(down))
    with pytest.raises(CatalogError):
        fetch_catalog(transport=FakeTransport(lambda: b"<html>"))


def test_load_catalog_normalizes_a_network_payload_and_writes_the_cache(ok, payload, cache_path):
    catalog = load_catalog(transport=FakeTransport(ok), cache_path=cache_path, now=lambda: 1.0)
    assert catalog.source == "network"
    assert catalog.fetched_at == 1_000
    assert len(catalog.models) == len(payload["data"])
    assert len(catalog.chat_models) == 15
    assert len(catalog.agent_models) == 14
    assert catalog.issues == []

    written = json.loads(cache_path.read_text())
    assert written["base_url"] == "https://api.vultrinference.com/v1"
    assert written["fetched_at"] == 1_000


def test_load_catalog_serves_a_fresh_cache_without_touching_the_network(ok, cache_path):
    load_catalog(transport=FakeTransport(ok), cache_path=cache_path, now=lambda: 1.0)

    second = FakeTransport(ok)
    catalog = load_catalog(transport=second, cache_path=cache_path, max_age=0.5, now=lambda: 1.4)
    assert catalog.source == "cache"
    assert catalog.fetched_at == 1_000
    assert second.calls == []

    expired = FakeTransport(ok)
    refreshed = load_catalog(transport=expired, cache_path=cache_path, max_age=0.5, now=lambda: 1.5)
    assert refreshed.source == "network"
    assert len(expired.calls) == 1


def test_load_catalog_falls_back_to_the_last_good_payload_when_the_network_fails(ok, payload, cache_path):
    load_catalog(transport=FakeTransport(ok), cache_path=cache_path, now=lambda: 1.0)

    catalog = load_catalog(transport=FakeTransport(down), cache_path=cache_path, now=lambda: 9.0)
    assert catalog.source == "stale-cache"
    assert catalog.fetched_at == 1_000
    assert len(catalog.models) == len(payload["data"])

    garbage = load_catalog(transport=FakeTransport(lambda: b'{"unexpected": true}'), cache_path=cache_path)
    assert garbage.source == "stale-cache"


def test_load_catalog_raises_catalog_error_when_there_is_no_cache_to_fall_back_to(cache_path):
    with pytest.raises(CatalogError):
        load_catalog(transport=FakeTransport(down), cache_path=cache_path)
    with pytest.raises(CatalogError):
        load_catalog(transport=FakeTransport(down))
    with pytest.raises(CatalogError):
        load_catalog(transport=FakeTransport(lambda: b'{"unexpected": true}'))


def test_load_catalog_ignores_a_foreign_cache_a_corrupt_cache_and_an_empty_payload(ok, cache_path, tmp_path):
    load_catalog(transport=FakeTransport(ok), cache_path=cache_path)
    with pytest.raises(CatalogError):
        load_catalog(transport=FakeTransport(down), cache_path=cache_path, base_url="https://other.test/v1")

    cache_path.write_text("{ not json")
    with pytest.raises(CatalogError):
        load_catalog(transport=FakeTransport(down), cache_path=cache_path)

    empty = tmp_path / "empty.json"
    load_catalog(transport=FakeTransport(lambda: b'{"data": []}'), cache_path=empty)
    with pytest.raises(CatalogError):
        load_catalog(transport=FakeTransport(down), cache_path=empty)

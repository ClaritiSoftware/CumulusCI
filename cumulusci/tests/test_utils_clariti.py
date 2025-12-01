import io
import json
from types import SimpleNamespace

import pytest

from cumulusci.utils.clariti import (
    ClaritiCheckoutResult,
    ClaritiError,
    build_default_org_name,
    checkout_org_from_pool,
    resolve_pool_id,
    set_sf_alias,
)


def _make_proc(*, stdout: str = "", stderr: str = "", returncode: int = 0):
    return SimpleNamespace(
        returncode=returncode,
        stdout_text=io.StringIO(stdout),
        stderr_text=io.StringIO(stderr),
    )


def test_resolve_pool_id_prefers_explicit():
    assert resolve_pool_id("Pool42", None) == "Pool42"


def test_resolve_pool_id_requires_config_when_missing(tmp_path):
    config_path = tmp_path / ".clariti.json"
    config_path.write_text("{}")

    resolved = resolve_pool_id(None, str(tmp_path))

    assert resolved is None


def test_resolve_pool_id_missing_file(tmp_path):
    with pytest.raises(ClaritiError) as exc:
        resolve_pool_id(None, str(tmp_path))

    message = str(exc.value)
    assert "pool id" in message
    assert ".clariti.json" in message


def test_checkout_org_from_pool_parses_username(monkeypatch):
    payload = {
        "orgId": "00D123",
        "username": "user@example.com",
        "alias": "foo",
        "poolId": "Pool42",
    }

    def fake_sfdx(command, **kwargs):
        assert command == "clariti org checkout"
        args = kwargs["args"]
        assert args[0] == "--json"
        assert "--pool-id" in args and "Pool42" in args
        assert "--alias" in args and "MyAlias" in args
        return _make_proc(stdout=json.dumps(payload))

    monkeypatch.setattr("cumulusci.utils.clariti.sfdx", fake_sfdx)

    result = checkout_org_from_pool("Pool42", alias="MyAlias")

    assert isinstance(result, ClaritiCheckoutResult)
    assert result.username == "user@example.com"
    assert result.alias == "foo"
    assert result.org_id == "00D123"
    assert result.pool_id == "Pool42"
    assert result.raw == payload


def test_checkout_org_from_pool_reads_nested_username(monkeypatch):
    payload = {
        "status": 0,
        "result": {
            "org": {"username": "nested@example.com"},
            "orgId": "00DNested",
        },
    }

    def fake_sfdx(command, **kwargs):
        assert "--pool-id" in kwargs["args"]
        return _make_proc(stdout=json.dumps(payload))

    monkeypatch.setattr("cumulusci.utils.clariti.sfdx", fake_sfdx)

    result = checkout_org_from_pool("PoolNested")

    assert result.username == "nested@example.com"
    assert result.org_id == "00DNested"
    assert result.alias is None


def test_checkout_org_from_pool_without_pool_id(monkeypatch):
    payload = {
        "username": "user@example.com",
        "poolId": "Pool-From-Config",
    }

    def fake_sfdx(command, **kwargs):
        assert "--pool-id" not in kwargs["args"]
        return _make_proc(stdout=json.dumps(payload))

    monkeypatch.setattr("cumulusci.utils.clariti.sfdx", fake_sfdx)

    result = checkout_org_from_pool(None)

    assert result.username == "user@example.com"


def test_checkout_org_from_pool_handles_failure(monkeypatch):
    def fake_sfdx(command, **kwargs):
        return _make_proc(stdout="", stderr="No orgs available", returncode=1)

    monkeypatch.setattr("cumulusci.utils.clariti.sfdx", fake_sfdx)

    with pytest.raises(ClaritiError) as exc:
        checkout_org_from_pool("EmptyPool")

    message = str(exc.value)
    assert "Clariti checkout failed" in message
    assert "No orgs available" in message


def test_checkout_org_from_pool_formats_json_error(monkeypatch):
    payload = {
        "name": "ClaritiOrgCheckoutError",
        "message": "Failed to get org from pool: No healthy orgs available in this pool",
    }

    def fake_sfdx(command, **kwargs):
        return _make_proc(stdout=json.dumps(payload), stderr="", returncode=1)

    monkeypatch.setattr("cumulusci.utils.clariti.sfdx", fake_sfdx)

    with pytest.raises(ClaritiError) as exc:
        checkout_org_from_pool("Pool42")

    message = str(exc.value)
    assert "Clariti checkout failed" in message
    assert "ClaritiOrgCheckoutError" in message
    assert "No healthy orgs" in message


def test_checkout_org_from_pool_formats_json_error_debug(monkeypatch):
    payload = {
        "name": "ClaritiOrgCheckoutError",
        "message": "Failed", "extra": "details",
    }

    def fake_sfdx(command, **kwargs):
        return _make_proc(stdout=json.dumps(payload), stderr="", returncode=1)

    monkeypatch.setattr("cumulusci.utils.clariti.sfdx", fake_sfdx)

    from cumulusci.core.debug import set_debug_mode

    with set_debug_mode(True):
        with pytest.raises(ClaritiError) as exc:
            checkout_org_from_pool("Pool42")

    message = str(exc.value)
    assert "Clariti checkout failed" in message
    assert "Clariti raw response" in message
    assert json.dumps(payload, indent=2, sort_keys=True) in message


def test_set_sf_alias_success(monkeypatch):
    def fake_sfdx(command, **kwargs):
        assert command == "alias set"
        assert kwargs["args"] == ["target=user@example.com"]
        return _make_proc()

    monkeypatch.setattr("cumulusci.utils.clariti.sfdx", fake_sfdx)

    success, message = set_sf_alias("target", "user@example.com")

    assert success is True
    assert message is None


def test_set_sf_alias_failure(monkeypatch):
    def fake_sfdx(command, **kwargs):
        return _make_proc(stdout="", stderr="Alias failure", returncode=1)

    monkeypatch.setattr("cumulusci.utils.clariti.sfdx", fake_sfdx)

    success, message = set_sf_alias("target", "username")

    assert success is False
    assert message is not None and message.startswith("Failed to set SF alias")
    assert "Alias failure" in message


def test_build_default_org_name_prefers_alias():
    assert build_default_org_name("user@example.com", "alias") == "alias"


def test_build_default_org_name_sanitizes_username():
    assert (
        build_default_org_name("user.with+symbol@example.com")
        == "user_with_symbol_example_com"
    )

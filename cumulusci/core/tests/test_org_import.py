from unittest import mock

from cumulusci.core.org_import import import_sfdx_org_to_keychain


def test_import_sfdx_org_to_keychain_detects_scratch(monkeypatch):
    scratch_org = mock.Mock()
    scratch_org.config = {}
    scratch_org.sfdx_info = {
        "org_id": "00D000000000001",
        "username": "user@example.com",
    }

    sfdx_config = mock.Mock()
    sfdx_config.sfdx_info = {
        "created_date": "2024-01-01T00:00:00.000Z",
        "expiration_date": "2024-01-05",
        "org_id": "00D000000000001",
        "username": "user@example.com",
    }

    monkeypatch.setattr(
        "cumulusci.core.org_import.SfdxOrgConfig",
        mock.Mock(return_value=sfdx_config),
    )
    monkeypatch.setattr(
        "cumulusci.core.org_import.ScratchOrgConfig",
        mock.Mock(return_value=scratch_org),
    )

    result = import_sfdx_org_to_keychain(
        mock.Mock(), "user@example.com", "my_org", global_org=False
    )

    assert result is scratch_org
    assert scratch_org.config["created"] is True
    assert scratch_org.config["days"] == 4
    assert "date_created" in scratch_org.config
    scratch_org.save.assert_called_once()


def test_import_sfdx_org_to_keychain_persistent(monkeypatch):
    sfdx_config = mock.Mock()
    sfdx_config.sfdx_info = {"created_date": None}

    monkeypatch.setattr(
        "cumulusci.core.org_import.SfdxOrgConfig",
        mock.Mock(return_value=sfdx_config),
    )
    monkeypatch.setattr(
        "cumulusci.core.org_import.ScratchOrgConfig",
        mock.Mock(),
    )

    result = import_sfdx_org_to_keychain(
        mock.Mock(), "user@example.com", "my_org", global_org=False
    )

    assert result is sfdx_config
    sfdx_config.populate_expiration_date.assert_called_once()
    sfdx_config.save.assert_called_once()

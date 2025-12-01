from __future__ import annotations

"""Shared helpers for importing orgs from the Salesforce CLI keychain."""

from datetime import datetime

from cumulusci.core.config.sfdx_org_config import SfdxOrgConfig
from cumulusci.core.config.scratch_org_config import ScratchOrgConfig
from cumulusci.utils import parse_api_datetime


def calculate_org_days(info: dict) -> int:
    """Return the lifetime of a scratch org in days based on CLI metadata."""

    if not info.get("created_date") or not info.get("expiration_date"):
        return 1

    created_date = parse_api_datetime(info["created_date"]).date()
    expires_date = datetime.strptime(info["expiration_date"], "%Y-%m-%d").date()
    return abs((expires_date - created_date).days)


def import_sfdx_org_to_keychain(
    keychain,
    username_or_alias: str,
    org_name: str,
    global_org: bool = False,
):
    """Import an org from the Salesforce CLI keychain into the provided keychain."""

    org_config = SfdxOrgConfig(
        {"username": username_or_alias, "sfdx": True},
        org_name,
        keychain,
        global_org,
    )

    # Suppress noisy logging while we hydrate from the Salesforce CLI keychain.
    org_config.print_json = False
    info = org_config.sfdx_info
    if info.get("created_date"):
        org_config = ScratchOrgConfig(
            {"username": username_or_alias}, org_name, keychain, global_org
        )
        org_config._sfdx_info = info
        org_config.config["created"] = True
        org_config.config["days"] = calculate_org_days(info)
        org_config.config["date_created"] = parse_api_datetime(info["created_date"])
        org_config.save()
    else:
        org_config.populate_expiration_date()
        org_config.save()

    return org_config

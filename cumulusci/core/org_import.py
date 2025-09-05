from datetime import datetime
from typing import Tuple

from cumulusci.core.config.sfdx_org_config import SfdxOrgConfig
from cumulusci.core.config.scratch_org_config import ScratchOrgConfig
from cumulusci.utils import parse_api_datetime


def calculate_org_days(info: dict) -> int:
    """Returns the difference in days between created_date (ISO 8601),
    and expiration_date (%Y-%m-%d). Falls back to 1 when unknown."""
    if not info.get("created_date") or not info.get("expiration_date"):
        return 1
    created_date = parse_api_datetime(info["created_date"]).date()
    expires_date = datetime.strptime(info["expiration_date"], "%Y-%m-%d").date()
    return abs((expires_date - created_date).days)


def import_sfdx_org_to_keychain(keychain, username_or_alias: str, org_name: str, global_org: bool = False):
    """Import an org from the Salesforce CLI (SFDX) keychain into the CCI keychain.

    Mirrors the logic used by the `cci org import` command without CLI side-effects.

    Returns the org_config that was saved in the keychain.
    """
    # Import the org from the SFDX keychain as an SfdxOrgConfig
    org_config = SfdxOrgConfig(
        {"username": username_or_alias, "sfdx": True}, org_name, keychain, global_org
    )

    info = org_config.sfdx_info
    if info.get("created_date"):
        # Re-import as a ScratchOrgConfig for locally-created scratch orgs
        org_config = ScratchOrgConfig(
            {"username": username_or_alias}, org_name, keychain, global_org
        )
        org_config._sfdx_info = info
        org_config.config["created"] = True
        org_config.config["days"] = calculate_org_days(info)
        org_config.config["date_created"] = parse_api_datetime(info["created_date"])
        org_config.save()
    else:
        # Persistent org or OAuth-imported scratch org
        org_config.populate_expiration_date()
        org_config.save()

    return org_config


"""Utilities for interacting with the Clariti Salesforce CLI plugin."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Tuple

import subprocess


class ClaritiError(Exception):
    """Raised when a Clariti CLI operation fails."""


@dataclass
class ClaritiCheckoutResult:
    """Information returned from a Clariti org checkout."""

    username: str
    alias: Optional[str]
    org_id: Optional[str]
    instance_url: Optional[str]
    org_type: Optional[str]
    pool_id: Optional[str]
    raw: Dict[str, Any]


def resolve_pool_id(pool_id: Optional[str], project_root: Optional[str]) -> Optional[str]:
    """Return the explicit pool id, ensuring Clariti config exists when omitted."""

    if pool_id:
        return pool_id

    if not project_root:
        raise ClaritiError(
            "No Clariti pool id provided. Provide --pool-id or add a .clariti.json "
            "file in the project root."
        )

    config_path = Path(project_root) / ".clariti.json"
    if not config_path.exists():
        raise ClaritiError(
            "No Clariti pool id provided. Provide --pool-id or ensure .clariti.json "
            "exists in the project root."
        )

    return None


_USERNAME_PATHS: Sequence[Sequence[str]] = (
    ("username",),
    ("result", "username"),
    ("result", "orgUsername"),
    ("result", "org", "username"),
    ("result", "user", "username"),
    ("result", "org", "userName"),
    ("org", "username"),
)

_ALIAS_PATHS: Sequence[Sequence[str]] = (
    ("alias",),
    ("result", "alias"),
    ("result", "orgAlias"),
    ("result", "org", "alias"),
)


def checkout_org_from_pool(
    pool_id: Optional[str],
    *,
    alias: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
) -> ClaritiCheckoutResult:
    """Checkout an org from the specified Clariti pool using the Salesforce CLI."""

    command = [
        "sf",
        "clariti",
        "org",
        "checkout",
        "--json",
    ]
    if pool_id:
        command.extend(["--pool-id", pool_id])
    if alias:
        command.extend(["--alias", alias])

    try:
        proc = subprocess.run(
            command,
            check=False,
            text=True,
            capture_output=True,
            env=env,
        )
    except FileNotFoundError as err:
        raise ClaritiError("Salesforce CLI 'sf' was not found on PATH.") from err

    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    if proc.returncode:
        message = stderr or stdout
        if not message:
            message = f"Command exited with return code {proc.returncode}"
        raise ClaritiError(message)

    if not stdout:
        raise ClaritiError("Clariti CLI did not return any data.")

    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as err:
        raise ClaritiError(
            "Failed to parse JSON from Clariti CLI response."
            f" Raw output: {stdout}"
        ) from err

    username = _extract_string(payload, _USERNAME_PATHS)
    alias_value = _extract_string(payload, _ALIAS_PATHS, allow_missing=True)
    org_id_value = _extract_string(
        payload, (("orgId",),), allow_missing=True
    )
    instance_url_value = _extract_string(
        payload, (("instanceUrl",),), allow_missing=True
    )
    org_type_value = _extract_string(
        payload, (("orgType",),), allow_missing=True
    )
    pool_id_value = _extract_string(
        payload, (("poolId",),), allow_missing=True
    )

    return ClaritiCheckoutResult(
        username=username,
        alias=alias_value,
        org_id=org_id_value,
        instance_url=instance_url_value,
        org_type=org_type_value,
        pool_id=pool_id_value,
        raw=payload,
    )


def set_sf_alias(
    alias: str, username: str, *, env: Optional[Dict[str, str]] = None
) -> Tuple[bool, Optional[str]]:
    """Set a Salesforce CLI alias for the provided username."""

    if not alias or not username:
        return False, "Alias and username are required."

    command = ["sf", "alias", "set", f"{alias}={username}"]
    try:
        proc = subprocess.run(
            command,
            check=False,
            text=True,
            capture_output=True,
            env=env,
        )
    except FileNotFoundError:
        return False, "Salesforce CLI 'sf' was not found on PATH."

    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    if proc.returncode:
        message = stderr or stdout
        if not message:
            message = f"Command exited with return code {proc.returncode}"
        return False, message

    return True, None


def _extract_string(
    payload: Dict[str, Any],
    paths: Sequence[Sequence[str]],
    *,
    allow_missing: bool = False,
) -> Optional[str]:
    """Extract the first non-empty string value found for the provided paths."""

    for path in paths:
        value: Any = payload
        for key in path:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                value = None
                break
        if isinstance(value, str) and value.strip():
            return value.strip()

    if allow_missing:
        return None

    raise ClaritiError("Unable to determine required field from Clariti response.")


def build_default_org_name(username: str, alias: Optional[str] = None) -> str:
    """Create a reasonable org name when Clariti checkout omits one."""

    if alias and alias.strip():
        return alias.strip()

    candidate = re.sub(r"[^A-Za-z0-9_]+", "_", username)
    candidate = candidate.strip("_") or "clariti_org"
    return candidate[:64]

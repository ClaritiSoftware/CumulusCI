"""Utilities for interacting with the Clariti Salesforce CLI plugin."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Tuple, cast

from cumulusci.core.sfdx import sfdx

from cumulusci.core.debug import get_debug_mode

class ClaritiError(Exception):
    """Raised when a Clariti CLI operation fails."""


@dataclass
class ClaritiCheckoutResult:
    """Information returned from a Clariti org checkout.

    :ivar username: Username associated with the checked-out org.
    :ivar alias: Alias assigned by Clariti, when present.
    :ivar org_id: Salesforce org identifier, if provided.
    :ivar instance_url: Instance URL for the org, when available.
    :ivar org_type: Salesforce org type metadata, if returned.
    :ivar pool_id: Clariti pool identifier for the checkout.
    :ivar raw: Raw JSON payload returned from the CLI.
    """

    username: str
    alias: Optional[str]
    org_id: Optional[str]
    instance_url: Optional[str]
    org_type: Optional[str]
    pool_id: Optional[str]
    raw: Dict[str, Any]


def resolve_pool_id(
    pool_id: Optional[str], project_root: Optional[str]
) -> Optional[str]:
    """Resolve the Clariti pool identifier for a checkout.

    :param pool_id: Optional pool id provided on the CLI.
    :param project_root: Path to the project root for locating ``.clariti.json``.
    :returns: ``pool_id`` when provided; ``None`` after verifying that
        ``.clariti.json`` exists; otherwise raises :class:`ClaritiError`.
    :raises ClaritiError: if neither ``pool_id`` is provided nor
        ``.clariti.json`` is present.
    """

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

_ORG_ID_PATHS: Sequence[Sequence[str]] = (
    ("orgId",),
    ("result", "orgId"),
    ("result", "org", "orgId"),
)


def checkout_org_from_pool(
    pool_id: Optional[str],
    *,
    alias: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
) -> ClaritiCheckoutResult:
    """Check out an org from Clariti using the Salesforce CLI.

    :param pool_id: Pool identifier to pass to the Clariti CLI, or ``None`` to
        defer to ``.clariti.json``.
    :param alias: Optional alias to set during checkout.
    :param env: Optional environment variables for the subprocess.
    :returns: Metadata describing the checked-out org.
    :raises ClaritiError: if the checkout command fails or returns invalid
        data.
    """

    command_args = ["--json"]
    if pool_id:
        command_args.extend(["--pool-id", pool_id])
    if alias:
        command_args.extend(["--alias", alias])

    try:
        proc = sfdx(
            "clariti org checkout",
            args=command_args,
            env=env,
            capture_output=True,
            check_return=False,
        )
    except FileNotFoundError as err:
        raise ClaritiError("Salesforce CLI 'sf' was not found on PATH.") from err
    except OSError as err:
        raise ClaritiError("Failed to execute Salesforce CLI 'sf'.") from err

    stdout = _read_process_stream(proc, "stdout_text", "stdout")
    stderr = _read_process_stream(proc, "stderr_text", "stderr")

    if proc.returncode:
        summary, raw_output = _summarize_error_output(stdout, stderr, proc.returncode)
        summary = f"Clariti checkout failed: {summary}"
        if get_debug_mode():
            raise ClaritiError(f"{summary}\nClariti raw response:\n{raw_output}")
        raise ClaritiError(summary)

    if not stdout:
        raise ClaritiError("Clariti CLI did not return any data.")

    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as err:
        raise ClaritiError(
            "Failed to parse JSON from Clariti CLI response."
            f" Raw output: {stdout}"
        ) from err

    username = cast(str, _extract_string(payload, _USERNAME_PATHS))
    alias_value = _extract_string(payload, _ALIAS_PATHS, allow_missing=True)
    org_id_value = _extract_string(payload, _ORG_ID_PATHS, allow_missing=True)
    instance_url_value = _extract_string(
        payload, (("instanceUrl",),), allow_missing=True
    )
    org_type_value = _extract_string(payload, (("orgType",),), allow_missing=True)
    pool_id_value = _extract_string(payload, (("poolId",),), allow_missing=True)

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
    """Set a Salesforce CLI alias for the provided username.

    :param alias: Desired alias name.
    :param username: Salesforce username to associate with the alias.
    :param env: Optional environment variables for the subprocess.
    :returns: Tuple of success flag and optional error message.
    """

    if not alias or not username:
        return False, "Alias and username are required."

    try:
        proc = sfdx(
            "alias set",
            args=[f"{alias}={username}"],
            env=env,
            capture_output=True,
            check_return=False,
        )
    except FileNotFoundError:
        return False, "Salesforce CLI 'sf' was not found on PATH."
    except OSError:
        return False, "Failed to execute Salesforce CLI 'sf'."

    stdout = _read_process_stream(proc, "stdout_text", "stdout")
    stderr = _read_process_stream(proc, "stderr_text", "stderr")
    if proc.returncode:
        summary, raw_output = _summarize_error_output(stdout, stderr, proc.returncode)
        summary = f"Failed to set SF alias: {summary}"
        if get_debug_mode():
            return False, f"{summary}\nClariti raw response:\n{raw_output}"
        return False, summary

    return True, None


def _read_process_stream(proc: Any, text_attr: str, raw_attr: str) -> str:
    """Normalize subprocess output attributes into plain text."""

    value = getattr(proc, text_attr, None)
    text = _coerce_stream_value(value)
    if not text:
        text = _coerce_stream_value(getattr(proc, raw_attr, None))
    return text.strip()


def _coerce_stream_value(value: Any) -> str:
    """Return a string representation from subprocess output containers."""

    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (bytes, bytearray)):
        return value.decode()
    getvalue = getattr(value, "getvalue", None)
    if callable(getvalue):
        result = getvalue()
        if isinstance(result, str):
            return result
        if isinstance(result, (bytes, bytearray)):
            return result.decode()
        return str(result)
    read = getattr(value, "read", None)
    if callable(read):
        position = value.tell() if hasattr(value, "tell") else None
        result = read()
        if position is not None and hasattr(value, "seek"):
            value.seek(position)
        if isinstance(result, str):
            return result
        if isinstance(result, (bytes, bytearray)):
            return result.decode()
        return str(result) if result is not None else ""
    return str(value)


def _extract_string(
    payload: Dict[str, Any],
    paths: Sequence[Sequence[str]],
    *,
    allow_missing: bool = False,
) -> Optional[str]:
    """Extract the first non-empty string value from the payload.

    :param payload: Data structure returned from Clariti.
    :param paths: Candidate key paths to inspect.
    :param allow_missing: Whether to return ``None`` when no value is found.
    :returns: The first matching string or ``None``.
    :raises ClaritiError: if no value is found and ``allow_missing`` is false.
    """

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
    """Create a reasonable org name when Clariti checkout omits one.

    :param username: Username returned by Clariti checkout.
    :param alias: Alias returned by Clariti checkout, if any.
    :returns: Sanitized org name suitable for the CCI keychain.
    """

    if alias and alias.strip():
        cleaned_alias = re.sub(r"[^A-Za-z0-9_]+", "_", alias)
        cleaned_alias = cleaned_alias.strip("_")
        if cleaned_alias:
            return cleaned_alias[:64]

    candidate = re.sub(r"[^A-Za-z0-9_]+", "_", username)
    candidate = candidate.strip("_") or "clariti_org"
    return candidate[:64]


def _summarize_error_output(
    stdout: str, stderr: str, returncode: int
) -> Tuple[str, str]:
    """Produce a concise error description and raw text for Clariti failures.

    :param stdout: Standard output captured from the Clariti subprocess.
    :param stderr: Standard error captured from the Clariti subprocess.
    :param returncode: Exit status of the subprocess.
    :returns: Tuple of (summary, formatted raw output).
    """

    raw_output = stderr or stdout
    if not raw_output:
        return (
            f"Clariti CLI exited with status {returncode} and no message.",
            "",
        )

    stripped = raw_output.strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return stripped, stripped

    if isinstance(parsed, dict):
        message = parsed.get("message") or parsed.get("error") or parsed.get("msg")
        code = parsed.get("code") or parsed.get("name") or parsed.get("status")
        if message and code:
            return f"{code}: {message}", json.dumps(parsed, indent=2, sort_keys=True)
        if message:
            return message, json.dumps(parsed, indent=2, sort_keys=True)
    return json.dumps(parsed, indent=2, sort_keys=True), json.dumps(
        parsed, indent=2, sort_keys=True
    )

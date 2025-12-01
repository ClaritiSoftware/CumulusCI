import contextlib
import io
import json
import logging
import os
import pathlib
import platform
import sys
import typing as T
from os import PathLike
from zipfile import ZipFile

import sarge

from cumulusci.core.enums import StrEnum
from cumulusci.core.exceptions import SfdxOrgException
from cumulusci.utils import temporary_dir

logger = logging.getLogger(__name__)


def _capture_to_text_stream(stream: T.Any, encoding: str) -> io.StringIO:
    """Convert a capture stream into a readable text buffer.

    sarge's Capture objects do not always implement ``flush`` on Windows,
    which breaks ``io.TextIOWrapper``. This helper normalizes the stream
    into an in-memory text buffer that supports the APIs the rest of CCI
    expects (``read``, iteration, etc.) without relying on ``flush``.
    """

    if stream is None:
        return io.StringIO("")

    data: T.Any = None
    getter = getattr(stream, "getvalue", None)
    if callable(getter):
        try:
            data = getter()
        except (AttributeError, IOError, OSError, ValueError):
            data = None
    if data is None:
        reader = getattr(stream, "read", None)
        if callable(reader):
            try:
                data = reader()
            except (AttributeError, IOError, OSError, ValueError):
                data = None

    if data is None:
        return io.StringIO("")
    if isinstance(data, str):
        return io.StringIO(data)
    if isinstance(data, (bytes, bytearray)):
        return io.StringIO(data.decode(encoding, errors="replace"))
    return io.StringIO(str(data))

def sfdx(
    command,
    username=None,
    log_note=None,
    access_token=None,
    args: T.Optional[T.Sequence[T.Any]] = None,
    env=None,
    capture_output=True,
    check_return=False,
):
    """Call an sfdx command and capture its output.

    Be sure to quote user input that is part of the command using `shell_quote`.

    Returns a `sarge` Command instance with returncode, stdout, stderr
    """
    command = f"sf {command}"
    if args is not None:
        for arg in args:
            if arg is None:
                raise SfdxOrgException(
                    "sfdx command received a None argument; "
                    "ensure all arguments are defined strings."
                )
            command += " " + shell_quote(str(arg))
    if username:
        command += f" -o {shell_quote(username)}"
    if log_note:
        logger.info(f"{log_note} with command: {command}")
    # Avoid logging access token
    if access_token:
        command += f" -o {shell_quote(access_token)}"
    env = env or {}
    p = sarge.Command(
        command,
        stdout=sarge.Capture(buffer_size=-1) if capture_output else None,
        stderr=sarge.Capture(buffer_size=-1) if capture_output else None,
        shell=True,
        env={**env, "SFDX_TOOL": "CCI"},
    )
    p.run()
    if capture_output:
        encoding = sys.stdout.encoding or sys.getdefaultencoding() or "utf-8"
        p.stdout_text = _capture_to_text_stream(p.stdout, encoding)
        p.stderr_text = _capture_to_text_stream(p.stderr, encoding)
    if check_return and p.returncode:
        message = f"Command exited with return code {p.returncode}"
        if capture_output:
            message += f":\n{p.stderr_text.read()}"
        raise Exception(message)
    return p


def shell_quote(s: str):
    if platform.system() == "Windows":
        assert isinstance(s, str)
        if not s:
            result = '""'
        elif '"' not in s:
            result = s
            if " " in result:
                result = f'"{result}"'
        else:
            escaped = s.replace('"', r"\"")
            result = f'"{escaped}"'

        return result
    else:
        return sarge.shell_quote(s)


def get_default_devhub_username():
    p = sfdx(
        "config get target-dev-hub --json",
        log_note="Getting default Dev Hub username from sfdx",
        check_return=True,
    )
    result = json.load(p.stdout_text)
    if "result" not in result or "value" not in result["result"][0]:
        raise SfdxOrgException(
            "No sf config found for target-dev-hub. "
            "Please use the sf config set to set the target-dev-hub and run again."
        )
    username = result["result"][0]["value"]
    return username


class SourceFormat(StrEnum):
    SFDX = "SFDX"
    MDAPI = "MDAPI"


def get_source_format_for_path(path: T.Optional[PathLike]) -> SourceFormat:
    if pathlib.Path(path or pathlib.Path.cwd(), "package.xml").exists():
        return SourceFormat.MDAPI

    return SourceFormat.SFDX


def get_source_format_for_zipfile(
    zf: ZipFile, subfolder: T.Optional[str]
) -> SourceFormat:
    namelist = zf.namelist()

    target_name = str(pathlib.PurePosixPath(subfolder or "", "package.xml"))

    if target_name in namelist:
        return SourceFormat.MDAPI

    return SourceFormat.SFDX


@contextlib.contextmanager
def convert_sfdx_source(
    path: T.Optional[PathLike], name: T.Optional[str], logger: logging.Logger
):
    mdapi_path = None
    with contextlib.ExitStack() as stack:
        # Convert SFDX -> MDAPI format if path exists but does not have package.xml
        if (
            len(os.listdir(path))  # path is None -> CWD
            and get_source_format_for_path(path) is SourceFormat.SFDX
        ):
            logger.info("Converting from SFDX to MDAPI format.")
            mdapi_path = stack.enter_context(temporary_dir(chdir=False))
            args = ["-d", mdapi_path]
            if path:
                # No path means convert default package directory in the CWD
                args += ["-r", str(path)]
            if name:
                args += ["-n", name]
            sfdx(
                "project convert source",
                args=args,
                capture_output=True,
                check_return=True,
            )

        yield mdapi_path or path

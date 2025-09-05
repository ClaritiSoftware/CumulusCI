import datetime
import json
import os
from typing import List, NoReturn, Optional

import sarge

from cumulusci.core.config import FAILED_TO_CREATE_SCRATCH_ORG
from cumulusci.core.config.sfdx_org_config import SfdxOrgConfig
from cumulusci.core.exceptions import (
    CumulusCIException,
    ScratchOrgException,
    ServiceNotConfigured,
)
from cumulusci.core.sfdx import sfdx
from cumulusci.utils import parse_api_datetime
from cumulusci.core.org_import import import_sfdx_org_to_keychain

import tempfile

class ScratchOrgConfig(SfdxOrgConfig):
    """Salesforce DX Scratch org configuration"""

    noancestors: bool
    # default = None  # what is this?
    instance: str
    password_failed: bool
    devhub: str
    release: str
    snapshot: str
    org_pool_id: str

    createable: bool = True

    @property
    def scratch_info(self):
        """Deprecated alias for sfdx_info.

        Will create the scratch org if necessary.
        """
        return self.sfdx_info

    @property
    def days(self) -> int:
        return self.config.setdefault("days", 1)

    @property
    def active(self) -> bool:
        """Check if an org is alive"""
        return self.date_created and not self.expired

    @property
    def expired(self) -> bool:
        """Check if an org has already expired"""
        return bool(self.expires) and self.expires < datetime.datetime.utcnow()

    @property
    def expires(self) -> Optional[datetime.datetime]:
        if self.date_created:
            return self.date_created + datetime.timedelta(days=int(self.days))

    @property
    def days_alive(self) -> Optional[int]:
        if self.date_created and not self.expired:
            delta = datetime.datetime.utcnow() - self.date_created
            return delta.days + 1

    def create_org(self) -> None:
        """Uses sf org create scratch  to create the org"""
        try:
            # If configured to use an org pool, checkout and import instead of creating
            pool_id = self.config.get("org_pool_id")
            if pool_id:
                alias = self.sfdx_alias or f"{getattr(getattr(self.keychain, 'project_config', None), 'project__name', '')}__{self.name}".strip("_")
                args: List[str] = []
                # pass pool id and alias
                args += ["-p", str(pool_id)]
                args += ["-n", alias]
                # Set default org if requested in config
                if self.default:
                    args += ["-s"]

                p: sarge.Command = sfdx(
                    "clariti org checkout --json",
                    args=args,
                    username=None,
                    log_note="Checking out org from pool",
                )
                stdout = p.stdout_text.read()
                stderr = p.stderr_text.read()

                if p.returncode:
                    message = f"Failed to checkout pooled org.\n{stdout}\n{stderr}"
                    raise ScratchOrgException(message)

                # Import the checked out org into CCI using shared import logic
                imported = import_sfdx_org_to_keychain(
                    self.keychain, alias, self.name, global_org=False
                )
                # Update this config to reflect the imported org
                info = imported.sfdx_info
                self.config.update(
                    {
                        "created": True,
                        "username": info.get("username"),
                        "org_id": info.get("org_id"),
                        "instance_url": info.get("instance_url"),
                    }
                )
                # days/date_created are already set in imported org where available
                if imported.config.get("days"):
                    self.config["days"] = imported.config.get("days")
                if imported.config.get("date_created"):
                    self.config["date_created"] = imported.config.get("date_created")

                # Do not reset password for pooled orgs
                return

            if not self.config_file:
                raise ScratchOrgException(
                    f"Scratch org config {self.name} is missing a config_file"
                )
            if not self.scratch_org_type:
                self.config["scratch_org_type"] = "workspace"

            args: List[str] = self._build_org_create_args()
            extra_args = os.environ.get("SFDX_ORG_CREATE_ARGS", "")
            p: sarge.Command = sfdx(
                f"org create scratch --json {extra_args}",
                args=args,
                username=None,
                log_note="Creating scratch org",
            )
            stdout = p.stdout_text.read()
            stderr = p.stderr_text.read()

            def raise_error() -> NoReturn:
                message = f"{FAILED_TO_CREATE_SCRATCH_ORG}: \n{stdout}\n{stderr}"
                try:
                    output = json.loads(stdout)
                    if (
                        output.get("message") == "The requested resource does not exist"
                        and output.get("name") == "NOT_FOUND"
                    ):
                        raise ScratchOrgException(
                            "The Salesforce CLI was unable to create a scratch org. Ensure you are connected using a valid API version on an active Dev Hub."
                        )
                except json.decoder.JSONDecodeError:
                    raise ScratchOrgException(message)

                raise ScratchOrgException(message)

            result = {}  # for type checker.
            if p.returncode:
                raise_error()
            try:
                result = json.loads(stdout)

            except json.decoder.JSONDecodeError:
                raise_error()

            if (
                not (res := result.get("result"))
                or ("username" not in res)
                or ("orgId" not in res)
            ):
                raise_error()

            if res["username"] is None:
                raise ScratchOrgException(
                    "SFDX claimed to be successful but there was no username "
                    "in the output...maybe there was a gack?"
                )

            self.config["org_id"] = res["orgId"]
            self.config["username"] = res["username"]

            self.config["date_created"] = datetime.datetime.utcnow()

            self.logger.error(stderr)

            self.logger.info(
                f"Created: OrgId: {self.config['org_id']}, Username:{self.config['username']}"
            )

            if self.config.get("set_password"):
                self.generate_password()

            # Flag that this org has been created
            self.config["created"] = True
        finally:
            # Clean up temporary config file if it exists
            if hasattr(self, '_tmp_config') and self._tmp_config and os.path.exists(self._tmp_config):
                try:
                    os.unlink(self._tmp_config)
                except Exception as e:
                    self.logger.warning(f"Failed to clean up temporary config file: {e}")

    def _build_org_create_args(self) -> List[str]:
        config_file = self.config_file
        self._tmp_config = None
        if self.snapshot and self.config_file:
            # When using snapshot, remove features, edition and snapshot from config
            with open(self.config_file, "r") as f:
                org_config = json.load(f)
                org_config.pop("features", None)
                org_config.pop("edition", None)
                org_config.pop("snapshot", None)

            # Create temporary config file
            tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
            self._tmp_config = tmp.name

            # Try catch error here to avoid leaving temp file around
            try:
                json.dump(org_config, tmp, indent=4)
                tmp.close()
                config_file = tmp.name
                self._tmp_config = config_file
            except Exception:
                tmp_name = tmp.name
                try:
                    tmp.close()
                except Exception:
                    pass
                if os.path.exists(tmp_name):
                    os.remove(tmp_name)
                raise

        args = ["-f", config_file, "-w", "120"]
        devhub_username: Optional[str] = self._choose_devhub_username()
        if devhub_username:
            args += ["--target-dev-hub", devhub_username]
        if not self.namespaced:
            args += ["--no-namespace"]
        if self.noancestors:
            args += ["--no-ancestors"]
        if self.days:
            args += ["--duration-days", str(self.days)]
        if self.release:
            args += [f"--release={self.release}"]
        if self.sfdx_alias:
            args += ["-a", self.sfdx_alias]
        with open(self.config_file, "r") as org_def:
            org_def_data = json.load(org_def)
            org_def_has_email = "adminEmail" in org_def_data
        if self.email_address and not org_def_has_email:
            args += [f"--admin-email={self.email_address}"]
        if self.default:
            args += ["--set-default"]
        if self.snapshot:
            args += [f"--snapshot={self.snapshot}"]

        return args

    def _choose_devhub_username(self) -> Optional[str]:
        """Determine which devhub username to specify when calling sfdx, if any."""
        # If a devhub was specified via `cci org scratch`, use it.
        # (This will return None if "devhub" isn't set in the org config,
        # in which case sf will use its target-dev-hub.)
        devhub_username = self.devhub
        if not devhub_username and self.keychain is not None:
            # Otherwise see if one is configured via the "devhub" service
            try:
                devhub_service = self.keychain.get_service("devhub")
            except (ServiceNotConfigured, CumulusCIException):
                pass
            else:
                devhub_username = devhub_service.username
        return devhub_username

    def generate_password(self) -> None:
        """Generates an org password with: sf org generate password.
        On a non-zero return code, set the password_failed in our config
        and log the output (stdout/stderr) from sfdx."""

        if self.password_failed:
            self.logger.warning("Skipping resetting password since last attempt failed")
            return

        p: sarge.Command = sfdx(
            "org generate password",
            self.username,
            log_note="Generating scratch org user password",
        )

        if p.returncode:
            self.config["password_failed"] = True
            stderr = p.stderr_text.readlines()
            stdout = p.stdout_text.readlines()
            # Don't throw an exception because of failure creating the
            # password, just notify in a log message
            nl = "\n"  # fstrings can't contain backslashes
            self.logger.warning(
                f"Failed to set password: \n{nl.join(stdout)}\n{nl.join(stderr)}"
            )

    def format_org_days(self) -> str:
        if self.days_alive:
            org_days = f"{self.days_alive}/{self.days}"
        else:
            org_days = str(self.days)
        return org_days

    def can_delete(self) -> bool:
        return bool(self.date_created)

    def delete_org(self) -> None:
        """Uses sf org delete scratch to delete the org"""
        if not self.created:
            self.logger.info("Skipping org deletion: the scratch org does not exist.")
            return

        p: sarge.Command = sfdx(
            "org delete scratch -p", self.username, "Deleting scratch org"
        )
        sfdx_output: List[str] = list(p.stdout_text) + list(p.stderr_text)

        for line in sfdx_output:
            if "error" in line.lower():
                self.logger.error(line)
            else:
                self.logger.info(line)

        if p.returncode:
            message = "Failed to delete scratch org"
            raise ScratchOrgException(message)

        # Flag that this org has been deleted
        self.config["created"] = False
        self.config["username"] = None
        self.config["date_created"] = None
        self.config["instance_url"] = None
        self.save()

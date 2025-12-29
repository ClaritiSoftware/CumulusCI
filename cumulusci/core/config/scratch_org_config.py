import datetime
import json
import os
import tempfile
from typing import List, NoReturn, Optional, TYPE_CHECKING, Union

import sarge

from cumulusci.core.config import FAILED_TO_CREATE_SCRATCH_ORG
from cumulusci.core.config.sfdx_org_config import SfdxOrgConfig
from cumulusci.core.exceptions import (
    CumulusCIException,
    ScratchOrgException,
    ServiceNotConfigured,
)
from cumulusci.core.sfdx import sfdx
from cumulusci.utils.clariti import ClaritiError, checkout_org_from_pool, set_sf_alias

if TYPE_CHECKING:  # pragma: no cover
    from cumulusci.core.org_import import import_sfdx_org_to_keychain as _Importer

import_sfdx_org_to_keychain = None  # type: ignore


def _get_org_importer():
    global import_sfdx_org_to_keychain
    if import_sfdx_org_to_keychain is None:
        from cumulusci.core.org_import import import_sfdx_org_to_keychain as helper

        import_sfdx_org_to_keychain = helper
    return import_sfdx_org_to_keychain

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
    @staticmethod
    def _as_aware_utc(dt: Union[datetime.datetime, datetime.date]) -> datetime.datetime:
        """Normalize datetimes to aware UTC for safe comparisons."""
        if isinstance(dt, datetime.date) and not isinstance(dt, datetime.datetime):
            dt = datetime.datetime.combine(dt, datetime.time.min)

        tzinfo = getattr(dt, "tzinfo", None)
        if tzinfo is None or tzinfo.utcoffset(dt) is None:
            return dt.replace(tzinfo=datetime.timezone.utc)

        return dt.astimezone(datetime.timezone.utc)

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
        expires = self.expires
        if not expires:
            return False

        expires = self._as_aware_utc(expires)
        now = datetime.datetime.now(datetime.timezone.utc)
        return expires < now

    @property
    def expires(self) -> Optional[datetime.datetime]:
        if self.date_created:
            expires = self.date_created + datetime.timedelta(days=int(self.days))
            return self._as_aware_utc(expires)

    @property
    def days_alive(self) -> Optional[int]:
        if self.date_created and not self.expired:
            created = self._as_aware_utc(self.date_created)
            delta = datetime.datetime.now(datetime.timezone.utc) - created
            return delta.days + 1

    def create_org(self) -> None:
        """Uses sf org create scratch  to create the org"""
        try:
            if (
                self.config.get("org_pool_id")
                and self._should_skip_pool_checkout_env()
            ):
                self.logger.info(
                    "Skipping Clariti org pool checkout because CCI_DISABLE_POOL_CHECKOUT "
                    "is set."
                )
            elif self._try_checkout_pooled_org():
                return
            if (
                self.config.get("org_pool_id")
                and os.getenv("CCI_DISABLE_SCRATCH_FALLBACK", "").lower()
                in ("1", "true", "yes", "on")
            ):
                self.logger.info(
                    "Clariti checkout failed and scratch org fallback is disabled via "
                    "CCI_DISABLE_SCRATCH_FALLBACK."
                )
                raise ScratchOrgException(
                    "Clariti checkout failed and scratch org fallback is disabled via "
                    "CCI_DISABLE_SCRATCH_FALLBACK."
                )
            if self.config.get("org_pool_id"):
                self.logger.info(
                    "Proceeding to create a new scratch org after Clariti checkout "
                    "failure."
                )
            self._create_org_via_sfdx()
        finally:
            self._cleanup_tmp_config()

    def _should_skip_pool_checkout_env(self) -> bool:
        value = os.getenv("CCI_DISABLE_POOL_CHECKOUT", "")
        return value.lower() in ("1", "true", "yes", "on")

    def _create_org_via_sfdx(self) -> None:
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
            except json.decoder.JSONDecodeError as e:
                raise ScratchOrgException(message) from e

            raise ScratchOrgException(message)

        result = {}  # for type checker.
        if p.returncode:
            raise_error()
        try:
            result = json.loads(stdout)
        except json.decoder.JSONDecodeError as e:
            try:
                raise_error()
            except ScratchOrgException as exc:
                raise exc from e

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
        self.config["date_created"] = datetime.datetime.now(datetime.timezone.utc)

        if stderr.strip():
            self.logger.debug("SFDX stderr: %s", stderr)
        self.logger.info(
            f"Created: OrgId: {self.config['org_id']}, Username:{self.config['username']}"
        )

        if self.config.get("set_password"):
            self.generate_password()

        self.config["created"] = True

    def _try_checkout_pooled_org(self) -> bool:
        pool_id = self.config.get("org_pool_id")
        if not pool_id or not self.keychain:
            return False

        alias = self.sfdx_alias
        if not alias:
            project_name = getattr(
                getattr(self.keychain, "project_config", None), "project__name", ""
            )
            alias = f"{project_name}__{self.name}".strip("_") or self.name

        try:
            checkout = checkout_org_from_pool(pool_id, alias=alias)
        except ClaritiError as err:
            suffix = f" from {pool_id}" if pool_id else ""
            self.logger.warning(
                "Failed to checkout pooled org%s: %s. Falling back to scratch creation.",
                suffix,
                err,
            )
            return False

        username = checkout.username
        if not username:
            self.logger.warning(
                "Clariti checkout did not return a username. "
                "Falling back to scratch creation."
            )
            return False

        if alias:
            success, alias_error = set_sf_alias(alias, username)
            if not success and alias_error:
                self.logger.warning(alias_error)

        importer = _get_org_importer()
        try:
            imported_org = importer(
                self.keychain, username, self.name, global_org=False
            )
        except Exception as err:
            self.logger.warning(
                "Failed to import Clariti org '%s': %s (%s). "
                "Falling back to scratch creation.",
                username,
                err,
                type(err).__name__,
            )
            return False

        if isinstance(imported_org, ScratchOrgConfig) and imported_org.expired:
            self.logger.warning(
                "Clariti provided an expired org for '%s'. Falling back to scratch "
                "creation.",
                username,
            )
            setter = getattr(self.keychain, "_set_org", None)
            if callable(setter):
                setter(self, self.global_org, save=False)
            return False

        self._configure_from_imported_org(imported_org, username, checkout.org_id)
        setter = getattr(self.keychain, "_set_org", None)
        if callable(setter):
            setter(self, self.global_org)
        # Persist the original scratch config (including metadata like config_name
        # and org_pool_id) after copying over the imported org details. The import
        # path writes a minimal SFDX config to the keychain, so we re-save the
        # full config here to avoid losing scratch metadata.
        if hasattr(imported_org, "_sfdx_info"):
            self._sfdx_info = imported_org._sfdx_info
            self._sfdx_info_date = getattr(imported_org, "_sfdx_info_date", None)
        self.save()

        if self.default and alias:
            try:
                sfdx(sarge.shell_format("config set target-org={}", alias))
            except Exception as exc:
                self.logger.warning(
                    "Failed to set Salesforce CLI default org '%s': %s",
                    alias,
                    exc,
                )

        return True

    def _configure_from_imported_org(
        self, imported_org, username: str, checkout_org_id: Optional[str] = None
    ) -> None:
        self.config["created"] = True
        self.config["username"] = imported_org.config.get("username") or username
        for key in ("org_id", "instance_url", "days", "date_created", "password"):
            if key in imported_org.config and imported_org.config[key] is not None:
                self.config[key] = imported_org.config[key]
        if checkout_org_id and not self.config.get("org_id"):
            self.config["org_id"] = checkout_org_id

        self.logger.info(
            "Checked out pooled org: OrgId: %s, Username:%s",
            self.config.get("org_id"),
            self.config.get("username"),
        )

    def _cleanup_tmp_config(self) -> None:
        tmp_path = getattr(self, "_tmp_config", None)
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except Exception as exc:
                self.logger.warning(
                    "Failed to clean up temporary config file %s: %s",
                    tmp_path,
                    exc,
                )
        self._tmp_config = None

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

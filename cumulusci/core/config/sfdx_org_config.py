import datetime
import json
import logging
from json.decoder import JSONDecodeError

from cumulusci.core.config import OrgConfig
from cumulusci.core.exceptions import SfdxOrgException
from cumulusci.core.sfdx import sfdx
from cumulusci.utils import get_git_config

logger = logging.getLogger(__name__)

nl = "\n"  # fstrings can't contain backslashes

# sf CLI 2.142.7+ redacts sensitive fields (access token, password) in
# `sf org display --json` output, replacing each value with a placeholder
# string that starts with this prefix. When we see it we transparently fetch
# the real value via the dedicated `sf org auth show-*` command.
REDACTED_VALUE_PREFIX = "[REDACTED]"


def _resolve_redacted_value(value, username, *, command, result_key, description):
    """Resolve a value that newer sf CLI redacts in ``org display`` output.

    Newer versions of the Salesforce CLI redact sensitive fields in
    ``sf org display --json`` output, replacing each value with a placeholder
    starting with ``[REDACTED]``. When that placeholder is detected, fetch the
    real value via ``command`` (whose JSON ``result`` object contains
    ``result_key``).

    For any non-redacted value (including ``None``/empty) the value is returned
    unchanged and no CLI call is made, keeping behavior identical on older sf
    CLI versions. ``description`` is a human-readable label used only in log
    and error messages.
    """
    if not value or not value.startswith(REDACTED_VALUE_PREFIX):
        return value

    logger.info(
        "Salesforce CLI redacted the %s for %s; fetching it via 'sf %s'",
        description,
        username,
        command,
    )
    p = sfdx(command, username)

    if p.returncode:
        # These commands are credential-adjacent: never log their raw
        # stdout/stderr, which can contain the secret itself or sensitive org
        # details. Log only the return code and keep the exception sanitized.
        logger.error("'sf %s' failed (returncode %s)", command, p.returncode)
        raise SfdxOrgException(
            f"Unable to resolve redacted {description} for {username} "
            f"(returncode {p.returncode})"
        )

    try:
        resolved = json.loads(p.stdout_text.read())["result"][result_key]
    except (JSONDecodeError, KeyError, TypeError) as e:
        raise SfdxOrgException(
            f"Failed to parse {description} from 'sf {command}' output for "
            f"{username} ({e.__class__.__name__})"
        )

    if not resolved or resolved.startswith(REDACTED_VALUE_PREFIX):
        raise SfdxOrgException(
            f"'sf {command}' returned an empty or still-redacted {description} "
            f"for {username}"
        )

    return resolved


def _resolve_access_token(access_token, username):
    """Resolve a redacted access token from ``sf org display`` output."""
    return _resolve_redacted_value(
        access_token,
        username,
        command="org auth show-access-token --no-prompt --json",
        result_key="accessToken",
        description="access token",
    )


def _resolve_password(password, username):
    """Resolve a redacted password from ``sf org display`` output."""
    return _resolve_redacted_value(
        password,
        username,
        command="org auth show-user-password --no-prompt --json",
        result_key="password",
        description="password",
    )


class SfdxOrgConfig(OrgConfig):
    """Org config which loads from sfdx keychain"""

    @property
    def sfdx_info(self):
        if hasattr(self, "_sfdx_info"):
            return self._sfdx_info

        # On-demand creation of scratch orgs
        if self.createable and not self.created:
            self.create_org()

        username = self.config.get("username")
        assert username is not None, "SfdxOrgConfig must have a username"
        if not self.print_json:
            self.logger.info(f"Getting org info from Salesforce CLI for {username}")

        # Call org display and parse output to get instance_url and
        # access_token
        p = sfdx("org display --json", self.username)

        org_info = None
        stderr_list = [line.strip() for line in p.stderr_text]
        stdout_list = [line.strip() for line in p.stdout_text]

        if p.returncode:
            self.logger.error(f"Return code: {p.returncode}")
            for line in stderr_list:
                self.logger.error(line)
            for line in stdout_list:
                self.logger.error(line)
            message = f"\nstderr:\n{nl.join(stderr_list)}"
            message += f"\nstdout:\n{nl.join(stdout_list)}"
            raise SfdxOrgException(message)

        else:
            try:
                org_info = json.loads("".join(stdout_list))
            except Exception as e:
                raise SfdxOrgException(
                    "Failed to parse json from output.\n  "
                    f"Exception: {e.__class__.__name__}\n  Output: {''.join(stdout_list)}"
                )
            access_token = _resolve_access_token(
                org_info["result"]["accessToken"], self.username
            )
            org_id = access_token.split("!")[0]

        sfdx_info = {
            "instance_url": org_info["result"]["instanceUrl"],
            "access_token": access_token,
            "org_id": org_id,
            "username": org_info["result"]["username"],
        }
        if org_info["result"].get("password"):
            sfdx_info["password"] = _resolve_password(
                org_info["result"]["password"], self.username
            )
        self._sfdx_info = sfdx_info
        self._sfdx_info_date = datetime.datetime.utcnow()
        self.config.update(sfdx_info)

        sfdx_info.update(
            {
                "created_date": org_info["result"].get("createdDate"),
                "expiration_date": org_info["result"].get("expirationDate"),
            }
        )
        return sfdx_info

    @property
    def access_token(self):
        return self.sfdx_info["access_token"]

    @property
    def instance_url(self):
        return self.config.get("instance_url") or self.sfdx_info["instance_url"]

    @property
    def org_id(self):
        org_id = self.config.get("org_id")
        if not org_id:
            org_id = self.sfdx_info["org_id"]
        return org_id

    @property
    def user_id(self):
        if not self.config.get("user_id"):
            result = self.salesforce_client.query_all(
                f"SELECT Id FROM User WHERE UserName='{self.username}'"
            )
            self.config["user_id"] = result["records"][0]["Id"]
        return self.config["user_id"]

    @property
    def username(self):
        username = self.config.get("username")
        if not username:
            username = self.sfdx_info["username"]
        return username

    @property
    def password(self):
        password = self.config.get("password")
        if not password:
            password = self.sfdx_info["password"]
        return password

    @property
    def email_address(self):
        email_address = self.config.get("email_address")
        if not email_address:
            email_address = get_git_config("user.email")
            self.config["email_address"] = email_address

        return email_address

    def get_access_token(self, **userfields):
        """Get the access token for a specific user

        If no keyword arguments are passed in, this will return the
        access token for the default user. If userfields has the key
        "username", the access token for that user will be returned.
        Otherwise, a SOQL query will be made based off of the
        passed-in fields to find the username, and the token for that
        username will be returned.

        Examples:

        | # default user access token:
        | token = org.get_access_token()

        | # access token for 'test@example.com'
        | token = org.get_access_token(username='test@example.com')

        | # access token for user based on lookup fields
        | token = org.get_access_token(alias='dadvisor')

        """
        if not userfields:
            # No lookup fields specified? Return the token for the default user
            return self.access_token

        # if we have a username, use it. Otherwise we need to do a
        # lookup using the passed-in fields.
        username = userfields.get("username", None)
        if username is None:
            where = [f"{key} = '{value}'" for key, value in userfields.items()]
            query = f"SELECT Username FROM User WHERE {' AND '.join(where)}"
            result = self.salesforce_client.query_all(query).get("records", [])
            if len(result) == 0:
                raise SfdxOrgException(
                    "Couldn't find a username for the specified user."
                )
            elif len(result) > 1:
                raise SfdxOrgException(
                    "More than one user matched the search critiera."
                )
            else:
                username = result[0]["Username"]

        p = sfdx(f"org display --target-org={username} --json")
        if p.returncode:
            output = p.stdout_text.read()
            try:
                info = json.loads(output)
                explanation = info["message"]
            except (JSONDecodeError, KeyError):
                explanation = output

            raise SfdxOrgException(
                f"Unable to find access token for {username}\n{explanation}"
            )
        else:
            info = json.loads(p.stdout_text.read())
            return _resolve_access_token(info["result"]["accessToken"], username)

    def force_refresh_oauth_token(self):
        # Call org display and parse output to get instance_url and
        # access_token
        p = sfdx("org open -r", self.username, log_note="Refreshing OAuth token")

        stdout_list = [line.strip() for line in p.stdout_text]

        if p.returncode:
            self.logger.error(f"Return code: {p.returncode}")
            for line in stdout_list:
                self.logger.error(line)
            message = f"Message: {nl.join(stdout_list)}"
            raise SfdxOrgException(message)

    # Added a print json argument to check whether it is there or not
    def refresh_oauth_token(self, keychain, print_json=False):
        """Use sfdx org display to refresh token instead of built in OAuth handling"""
        if hasattr(self, "_sfdx_info"):
            # Cache the sfdx_info for 1 hour to avoid unnecessary calls out to sfdx CLI
            delta = datetime.datetime.utcnow() - self._sfdx_info_date
            if delta.total_seconds() > 3600:
                del self._sfdx_info

                # Force a token refresh
                self.force_refresh_oauth_token()
        self.print_json = print_json
        # Get org info via sf org display
        self.sfdx_info
        # Get additional org info by querying API
        self._load_orginfo()

# Environment Variables

CumulusCI has environment variables that are useful when CumulusCI is
being run inside of web applications, such as MetaCI, MetaDeploy, and
Metecho. The following is a reference list of available environment
variables that can be set.

## `CUMULUSCI_AUTO_DETECT`

Set this environment variable to autodetect branch and commit
information from `HEROKU_TEST_RUN_BRANCH` and
`HEROKU_TEST_RUN_COMMIT_VERSION` environment variables.

## `CUMULUSCI_DISABLE_REFRESH`

If present, will instruct CumulusCI to not refresh OAuth tokens for
orgs.

## `CUMULUSCI_KEY`

An alphanumeric string used to encrypt org credentials at rest when an
OS keychain is not available.

## `CUMULUSCI_REPO_URL`

Used for specifying a GitHub Repository for CumulusCI to use when
running in a CI environment.

(cumulusci-system-certs)=
## `CUMULUSCI_SYSTEM_CERTS`

If set to `True`, CumulusCI will configure the Python `requests` library
to validate server TLS certificates using the system's certificate
authorities, instead of the set of CA certs that is bundled with
`requests`.

## `GITHUB_APP_ID`

Your GitHub App's identifier.

## `GITHUB_APP_KEY`

Contents of a JSON Web Token (JWT) used to [authenticate a GitHub
app](https://developer.github.com/apps/building-github-apps/authenticating-with-github-apps/##authenticating-as-a-github-app).

(github-token)=
## `GITHUB_TOKEN`

A GitHub [personal access
token](https://help.github.com/en/github/authenticating-to-github/creating-a-personal-access-token-for-the-command-line).

## `HEROKU_TEST_RUN_BRANCH`

Used for specifying a specific branch to test against in a Heroku CI
environment

## `HEROKU_TEST_RUN_COMMIT_VERSION`

Used to specify a specific commit to test against in a Heroku CI
environment.

## `SFDX_CLIENT_ID`

Client ID for a Connected App used to authenticate to a persistent org,
e.g. a Developer Hub. Set with SFDX_HUB_KEY.

## `SFDX_HUB_KEY`

Contents of JSON Web Token (JWT) used to authenticate to a persistent
org, e.g. a Dev Hub. Set with SFDX_CLIENT_ID.

## `SFDX_ORG_CREATE_ARGS`

Extra arguments passed to `sf org create scratch`.

To provide additional arguments, use the following format. For instance, to set the release to "preview", the environment variable would be: "--release=preview"

To specify multiple options, you can include them together, like: "--edition=developer --release=preview"

(telemetry)=
## Telemetry

CumulusCI includes optional error telemetry powered by Sentry to help improve
the tool. Telemetry is **disabled by default** and must be explicitly enabled.

### `CCI_ENABLE_TELEMETRY`

Set to `1`, `true`, or `yes` to enable error telemetry. When enabled, CumulusCI
will send anonymous error reports to help developers identify and fix issues.

```bash
export CCI_ENABLE_TELEMETRY=1
```

### `CCI_ENVIRONMENT`

Override the environment tag sent with telemetry data. By default, CumulusCI
automatically detects whether it's a development or production release based
on the version string.

### `SENTRY_DSN`

Override the default Sentry DSN endpoint. This is primarily useful for
organizations that want to route telemetry to their own Sentry instance.

### What data is collected?

When telemetry is enabled, CumulusCI collects:

- **Error information**: Exception type, message, and stack trace
- **CumulusCI version**: The installed version of CumulusCI
- **Environment**: Whether running a development or production build
- **Anonymous user ID**: A hashed identifier based on machine characteristics
  (hostname, architecture, processor) - no personally identifiable information
- **OS information**: Operating system name, version, and architecture
- **CI environment**: Which CI platform is being used (if any)

CumulusCI does **not** collect:

- Salesforce credentials or tokens
- Org data or metadata
- Project-specific configuration
- File contents or paths
- Personal information

### Disabling telemetry

Telemetry is disabled by default. If you previously enabled it and want to
disable it, simply unset or remove the `CCI_ENABLE_TELEMETRY` environment
variable.

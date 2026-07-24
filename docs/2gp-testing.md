# Testing with Second-Generation Packaging

CumulusCI makes it easy to harness the power of second-generation
managed packages to implement an advanced, comprehensive testing process
for _both_ first- and second-generation managed package products.

This process yields multiple benefits:

-   You can test managed packages _as_ managed packages, but before
    merging code.
-   You gain the ability to perform end-to-end testing across
    applications that span multiple packages earlier in the development
    lifecycle.
-   For existing 1GP products, it also allows for the creation of a
    full-scale 2GP testing and development framework _before_ migrating
    products from 1GP to 2GP. Migration, when generally available, will
    be much easier because products are already being tested as 2GPs.

Salesforce.org is actively using this process for feature-level testing
and end-to-end testing of dozens of existing first-generation packages,
while preparing for the migration into second-generation packaging. This
process is also applicable for testing products that started as
second-generation packages.

## Building 2GP Beta Packages in Continuous Integration

Any managed package product - first or second generation - can use
CumulusCI automation to build and test 2GP beta packages. The
out-of-the-box flow `build_feature_test_package` can be run on any
commit. This flow builds a 2GP beta package using an alternate package
name (which defaults to `<project name> Managed Feature Test`,
reflecting its intended role in supporting feature-branch testing) but
with the same namespace as the main package.

The 2GP test package is also built using the `Skip Validation` option,
which defers validation of the package until install time. Skipping
validation ensures that feature test packages build extremely quickly,
and also avoids locking in dependency versions - making it easy to
achieve complex end-to-end testing workflows, as described in
[End-to-End Testing with Second-Generation
Packages](end-to-end-testing-with-second-generation-packages).

CumulusCI stores data about feature test packages in GitHub
commit-status messages. When the `build_feature_test_package` flow
completes successfully, the `04t` id of the created package version is
stored in the "Build Feature Test Package" commit status on GitHub.
Testing and 2GP build flows can acquire the package version from this
store.

## 2GP Tests for Feature Branches

The `ci_feature_2gp` flow parallels `ci_feature`, which is used for
unmanaged feature testing in continuous integration, but uses a 2GP
feature test package instead of deploying the project unmanaged.

When executed on a specific commit, the flow acquires a 2GP feature test
package id from the "Build Feature Test Package" commit status on that
commit. It installs that package, then executes Apex unit tests.

```{note}
The `ci_feature_2gp` flow is intended for use after the
`build_feature_test_package` flow. On MetaCI, this is implemented by
using a Commit Status trigger to run `ci_feature_2gp`; on other CI
systems, a `ci_feature_2gp` build may be made dependent on a
`build_feature_test_package` build.
```

Running 2GP tests in CI can replace the use of namespaced scratch orgs
for most automated testing objectives. 2GP testing orgs provide a more
accurate representation of how namespaces are applied and how metadata
will behave once packaged, making it possible to catch packaging-related
issues _before_ code is merged to the main branch or deployed to a 1GP
packaging org.

```{note}
Component coverage for first- and second-generation packages is very
similar, but some projects may use components with differing behaviors.
Consult the [Metadata Coverage
Report](https://developer.salesforce.com/docs/metadata-coverage) with
any questions.
```

Manual QA can be executed on feature branches via the flow `qa_org_2gp`,
which operates just like `ci_feature_2gp` but which also executes
`config_qa` to prepare an org for manual testing. Similarly, Robot tests
may be executed against 2GP orgs by running `qa_org_2gp` instead of
`qa_org` before invoking `robot`.

## Feature and Epic Branch Betas via Annotated Git Tags

The commit-status process above targets `feature/NNN` release branches.
For arbitrarily named feature or epic branches (for example
`epic/new-billing`), CumulusCI can instead record a 2GP beta as
an **annotated git tag** and resolve it when building an org from that
branch. This lets QA and developers spin up a scratch org seeded with the
in-flight package version for a specific branch without hand-specifying a
`version_id`.

Feature-branch betas are recorded as annotated git tags **only**, never
as GitHub Releases. This is deliberate: a feature-branch GitHub Release
would be returned as the global "latest beta" to every consumer of the
`include_beta` and `commit_status` strategies, a silent cross-repository
regression. Annotated tags are read through the git refs API and are
invisible to every Release-based resolver.

### Building and recording the beta

1.  Build the 2GP package version. To give a branch its own build-number
    sequence, pass the `branch` option to `create_package_version`. This
    sets the `Branch` field on the `Package2VersionCreateRequest`, and
    Salesforce scopes the build counter independently per
    `(package, major.minor.patch, branch)`. The option is opt-in: when it
    is omitted the `Branch` field is not set and counting is unscoped,
    exactly as before.

    ```console
    $ cci task run create_package_version --branch epic/new-billing
    ```

2.  Record the resulting version as an annotated git tag with the
    `create_feature_branch_tag` task. Pass the same `--branch` so the tag
    is created under the intended prefix regardless of the current
    checkout. The tag is named `<branch>/<version>` (for example
    `epic/new-billing/1.2.0.1`) and embeds the `version_id` (`04t`) in its
    message. No GitHub Release is created.

    ```console
    $ cci task run create_feature_branch_tag \
        --branch epic/new-billing \
        --version 1.2.0.1 \
        --version-id 04tXXXXXXXXXXXXXXX
    ```

### Building an org from the beta

Run the `feature_org` flow, which uses the `feature_branch` resolution
strategy. When run from a repository already checked out on the feature
branch, the branch is detected automatically:

```console
$ cci flow run feature_org --org feature
```

For a repository that stays on `main` (such as a solution-org project
that aggregates many dependencies), name the branch explicitly. Every
dependency repository that has a matching feature-branch tag resolves to
it; those that do not fall through to the latest beta and then the latest
release, so mixed sets of dependencies resolve correctly:

```console
$ cci flow run feature_org --org feature \
    -o update_dependencies.feature_branch=epic/new-billing
```

See [Controlling GitHub Dependency Resolution](controlling-github-dependency-resolution)
for the full ordered list of resolvers in the `feature_branch` strategy.

### Declaring the dependency in `cumulusci.yml`

A downstream project can consume a branch beta through its
`cumulusci.yml` in two ways.

To install one specific branch beta deterministically, pin the annotated
tag on a GitHub dependency. Because the tag carries the package
`version_id` in its message, the `tag` resolver installs exactly that
second-generation package version, with no resolution strategy involved:

```yaml
project:
    dependencies:
        - github: https://github.com/example-org/example-package
          tag: epic/new-billing/1.2.0.1
```

To resolve the newest branch beta dynamically instead of pinning a fixed
version, point a resolution alias at the `feature_branch` strategy so
development flows use it, then supply the branch at run time:

```yaml
project:
    dependency_resolutions:
        preproduction: feature_branch
        production: latest_release
```

```console
$ cci flow run dev_org --org dev \
    -o update_dependencies.feature_branch=epic/new-billing
```

When no feature branch is supplied, the strategy falls through to the
latest beta and then the latest release, so it is safe to leave
configured as a default.

To resolve the newest branch beta for a *specific* dependency, set the
`feature_branch` field directly on that dependency. This is useful when
different dependencies track different branches, or when only one
dependency should follow a branch while the rest use their normal
resolution:

```yaml
project:
    dependencies:
        - github: https://github.com/example-org/package-a
          feature_branch: epic/new-billing
        - github: https://github.com/example-org/package-b
          feature_branch: epic/other-work
        - github: https://github.com/example-org/package-c
```

The dependency's `feature_branch` takes precedence over any run-wide
`feature_branch` option and over the current branch. Package C, with no
`feature_branch`, resolves normally (latest beta, then release). This
still requires the `feature_branch` strategy to be active (via the
`feature_org` flow, a resolution alias, or the `resolution_strategy`
option).

(end-to-end-testing-with-second-generation-packages)=

## End-to-End Testing with Second-Generation Packages

The `qa_org_2gp` flow allows for performing manual and automated
end-to-end tests of multi-package products sooner in the development
lifecycle then was previously possible. Take the following example:

-   Product B has a dependency on Product A.
-   Product B is developing a new feature that is dependent on a new
    feature being developed for Product A.

Without the ability to test with 2GP packages, end-to-end testing on
Product A and B's linked features could only occur once both products
have moved significantly forward in the development lifecycle:

-   Both A and B merge their feature work into their main branch in a
    source control system.
-   New feature metadata is uploaded to the packaging org, if the
    products are 1GPs.
-   New beta versions for both Product A and B are created
-   In many cases, a production release for Product A must also be
    created to satisfy B's dependency, if the packages are 1GPs.

Once all of the steps above have occurred, end-to-end testing with new
managed package versions can take place. However, if _any_ errors are
found at this point the entire process has to start over again, and
first-generation packages may have already incurred component lock-in.
With 2GP testing, this is no longer the case.

Instead, a tester may execute the `qa_org_2gp` flow from a feature
branch in the repository of Product B. The following will occur:

1.  CumulusCI resolves dependencies as they are defined Product B's
    `cumulusci.yml` file, using the `commit_status` resolution strategy.
    CumulusCI matches the current branch and release against branches in
    the upstream dependencies to locate the most relevant 2GP packages
    for this testing process. See [](controlling-github-dependency-resolution) for more
    details.
2.  CumulusCI installs suitable 2GP feature test packages for Product A
    and any other dependencies, if found, or falls back to 1GP packages
    if not found.
3.  CumulusCI installs a Project B 2GP feature test package, sourced
    from a GitHub commit status on the current commit. (The commit must
    have been pushed, and `build_feature_test_package` must have run
    successfully).
4.  Finally, CumulusCI executes the `config_qa` flow to prepare the org
    for use in testing.

This allows for full end-to-end testing of features that have
inter-package-dependencies prior to the merging of code to any
long-lived branches (e.g. a release branch or `main`). Because CumulusCI
defaults to building packages using `Skip Validation`, any suitable 2GP
feature test package installed for Project A may satisfy the dependency,
making it possible to test feature development without committing to
package version numbers or specific dependency versions.

The process, backed by second-generation packaging, maximizes the
utility of feature-level testing processes for both first- and
second-generation packages, while helping prepare first-generation
packages to migrate to 2GP once migration becomes generally available.

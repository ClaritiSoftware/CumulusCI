from typing import List, Optional, Tuple
from unittest import mock

import pytest
from github3.exceptions import NotFoundError

from cumulusci.core.config import UniversalConfig
from cumulusci.core.config.project_config import BaseProjectConfig
from cumulusci.core.config.tests.test_config import DummyRelease
from cumulusci.core.dependencies.dependencies import (
    DynamicDependency,
    GitHubDependencyPin,
    GitHubDynamicDependency,
    PackageNamespaceVersionDependency,
    PackageVersionIdDependency,
    StaticDependency,
    UnmanagedGitHubRefDependency,
)
from cumulusci.core.dependencies.resolvers import (
    AbstractGitHubReleaseBranchResolver,
    DependencyResolutionStrategy,
    GitHubBetaReleaseTagResolver,
    GitHubDefaultBranch2GPResolver,
    GitHubExactMatch2GPResolver,
    GitHubFeatureBranchTagResolver,
    GitHubReleaseBranchCommitStatusResolver,
    GitHubReleaseTagResolver,
    GitHubTagResolver,
    GitHubUnmanagedHeadResolver,
    dependency_filter_ignore_deps,
    get_release_id,
    get_resolver,
    get_resolver_stack,
    get_static_dependencies,
    locate_commit_status_package_id,
)
from cumulusci.core.exceptions import CumulusCIException, DependencyResolutionError


class ConcreteDynamicDependency(DynamicDependency):
    ref: Optional[str] = None
    resolved: Optional[bool] = False

    @property
    def is_resolved(self):
        return self.resolved

    def resolve(
        self, context: BaseProjectConfig, strategies: List[DependencyResolutionStrategy]
    ):
        super().resolve(context, strategies)
        self.resolved = True

    @property
    def name(self):
        return ""

    @property
    def description(self):
        return ""


class TestGitHubTagResolver:
    def test_github_tag_resolver(self, project_config):
        tag = mock.Mock()
        tag.return_value.object.sha = "tag_sha"
        tag.return_value.message = """
package_type: 1GP

version_id: 04t000000000000"""
        project_config.get_repo_from_url(
            "https://github.com/SFDO-Tooling/ReleasesRepo"
        ).tag = tag
        dep = GitHubDynamicDependency(
            github="https://github.com/SFDO-Tooling/ReleasesRepo",
            tag="release/1.0",  # Not the most recent release
        )
        resolver = GitHubTagResolver()

        assert resolver.can_resolve(dep, project_config)
        assert resolver.resolve(dep, project_config) == (
            "tag_sha",
            PackageNamespaceVersionDependency(
                namespace="ccitestdep",
                version="1.0",
                package_name="CumulusCI-Test-Dep",
                version_id="04t000000000000",
            ),
        )

    def test_github_tag_resolver__2gp(self, project_config):
        tag = mock.Mock()
        tag.return_value.object.sha = "tag_sha"
        tag.return_value.message = """
package_type: 2GP

version_id: 04t000000000000"""
        project_config.get_repo_from_url(
            "https://github.com/SFDO-Tooling/ReleasesRepo"
        ).tag = tag

        dep = GitHubDynamicDependency(
            github="https://github.com/SFDO-Tooling/ReleasesRepo",
            tag="release/1.0",  # Not the most recent release
        )
        resolver = GitHubTagResolver()

        assert resolver.can_resolve(dep, project_config)
        assert resolver.resolve(dep, project_config) == (
            "tag_sha",
            PackageVersionIdDependency(
                version_id="04t000000000000",
                version_number="1.0",
                package_name="CumulusCI-Test-Dep",
            ),
        )

    def test_github_tag_resolver__2gp_no_namespace(self, project_config):
        tag = mock.Mock()
        tag.return_value.object.sha = "tag_sha"
        tag.return_value.message = """
package_type: 2GP

version_id: 04t000000000000"""
        project_config.get_repo_from_url(
            "https://github.com/SFDO-Tooling/UnmanagedRepo"
        ).tag = tag

        # UnmanagedRepo contains a release but no namespace,
        # and we mock out the tag details for an Unlocked,
        # no-namespace 2GP above.
        dep = GitHubDynamicDependency(
            github="https://github.com/SFDO-Tooling/UnmanagedRepo",
            tag="release/1.0",  # Not the most recent release
        )
        resolver = GitHubTagResolver()

        assert resolver.can_resolve(dep, project_config)
        assert resolver.resolve(dep, project_config) == (
            "tag_sha",
            PackageVersionIdDependency(
                version_id="04t000000000000",
                version_number="1.0",
                package_name="CumulusCI-Test",
            ),
        )

    def test_github_tag_resolver__unmanaged(self, project_config):
        dep = GitHubDynamicDependency(
            github="https://github.com/SFDO-Tooling/ReleasesRepo",
            tag="release/2.0",
            unmanaged=True,
        )
        resolver = GitHubTagResolver()

        assert resolver.resolve(dep, project_config) == (
            "tag_sha",
            None,
        )

    def test_no_managed_release(self, project_config):
        dep = GitHubDynamicDependency(
            github="https://github.com/SFDO-Tooling/UnmanagedRepo",  # This repo has no namespace
            tag="release/1.0",
            unmanaged=False,
        )
        resolver = GitHubTagResolver()

        assert resolver.resolve(dep, project_config) == (
            "tag_sha",
            None,
        )

    def test_can_resolve_negative(self, project_config):
        dep = GitHubDynamicDependency(
            github="https://github.com/SFDO-Tooling/ReleasesRepo"
        )
        resolver = GitHubTagResolver()

        assert not resolver.can_resolve(dep, project_config)

    def test_exception_no_tag_found(self, project_config):
        dep = GitHubDynamicDependency(
            github="https://github.com/SFDO-Tooling/ReleasesRepo",
            tag="release/3.0",
        )
        resolver = GitHubTagResolver()

        with pytest.raises(DependencyResolutionError) as e:
            resolver.resolve(dep, project_config)
        assert "No release found for tag" in str(e.value)

    def test_str(self):
        assert str(GitHubTagResolver()) == GitHubTagResolver.name


class TestGitHubReleaseTagResolver:
    def test_github_release_tag_resolver(self, project_config):
        tag = mock.Mock()
        tag.return_value.object.sha = "tag_sha"
        tag.return_value.message = """
package_type: 1GP

version_id: 04t000000000000"""
        project_config.get_repo_from_url(
            "https://github.com/SFDO-Tooling/ReleasesRepo"
        ).tag = tag
        dep = GitHubDynamicDependency(
            github="https://github.com/SFDO-Tooling/ReleasesRepo"
        )
        resolver = GitHubReleaseTagResolver()

        assert resolver.can_resolve(dep, project_config)
        assert resolver.resolve(dep, project_config) == (
            "tag_sha",
            PackageNamespaceVersionDependency(
                namespace="ccitestdep",
                version="2.0",
                package_name="CumulusCI-Test-Dep",
                version_id="04t000000000000",
            ),
        )

    def test_github_release_tag_resolver__2gp(self, project_config):
        tag = mock.Mock()
        tag.return_value.object.sha = "tag_sha"
        tag.return_value.message = """
package_type: 2GP

version_id: 04t000000000000"""
        project_config.get_repo_from_url(
            "https://github.com/SFDO-Tooling/TwoGPRepo"
        ).tag = tag

        dep = GitHubDynamicDependency(
            github="https://github.com/SFDO-Tooling/TwoGPRepo"
        )
        resolver = GitHubReleaseTagResolver()

        assert resolver.can_resolve(dep, project_config)
        assert resolver.resolve(dep, project_config) == (
            "tag_sha",
            PackageVersionIdDependency(
                version_id="04t000000000000",
                version_number="1.0",
                package_name="CumulusCI-2GP-Test",
            ),
        )

    def test_github_release_tag_resolver__2gp_no_namespace(self, project_config):
        tag = mock.Mock()
        tag.return_value.object.sha = "tag_sha"
        tag.return_value.message = """
package_type: 2GP

version_id: 04t000000000000"""
        project_config.get_repo_from_url(
            "https://github.com/SFDO-Tooling/UnmanagedRepo"
        ).tag = tag

        # UnmanagedRepo contains a release but no namespace,
        # and we mock out the tag details for an Unlocked,
        # no-namespace 2GP above.
        dep = GitHubDynamicDependency(
            github="https://github.com/SFDO-Tooling/UnmanagedRepo",
        )
        resolver = GitHubReleaseTagResolver()

        assert resolver.can_resolve(dep, project_config)
        assert resolver.resolve(dep, project_config) == (
            "tag_sha",
            PackageVersionIdDependency(
                version_id="04t000000000000",
                version_number="1.0",
                package_name="CumulusCI-Test",
            ),
        )

    @mock.patch("cumulusci.core.dependencies.resolvers.find_latest_release")
    def test_beta_release_tag(self, get_latest, project_config):
        get_latest.return_value = DummyRelease("beta/2.1_Beta_1", "2.1 Beta 1")
        dep = GitHubDynamicDependency(
            github="https://github.com/SFDO-Tooling/ReleasesRepo"
        )
        resolver = GitHubBetaReleaseTagResolver()
        assert resolver.can_resolve(dep, project_config)
        resolved = resolver.resolve(dep, project_config)

        assert resolved == (
            "tag_sha",
            PackageNamespaceVersionDependency(
                namespace="ccitestdep",
                version="2.1 Beta 1",
                package_name="CumulusCI-Test-Dep",
            ),
        )

    def test_no_managed_release(self, project_config):
        dep = GitHubDynamicDependency(
            github="https://github.com/SFDO-Tooling/UnmanagedRepo",  # This repo has no namespace
            tag="release/1.0",
            unmanaged=False,
        )
        resolver = GitHubTagResolver()

        assert resolver.resolve(dep, project_config) == (
            "tag_sha",
            None,
        )

    def test_not_found(self, project_config):
        dep = GitHubDynamicDependency(
            github="https://github.com/SFDO-Tooling/NoReleasesRepo"
        )
        resolver = GitHubReleaseTagResolver()

        assert resolver.can_resolve(dep, project_config)
        assert resolver.resolve(dep, project_config) == (None, None)


class TestGitHubFeatureBranchTagResolver:
    def _make_context(
        self, active=None, repo_branch=None, default_branch="main", prefix="feature/"
    ):
        context = mock.Mock()

        def lookup(name, *args, **kwargs):
            if name == "project__git__active_feature_branch":
                return active
            return None

        context.lookup.side_effect = lookup
        context.repo_branch = repo_branch
        context.project__git__default_branch = default_branch
        context.project__git__prefix_feature = prefix
        return context

    def _dep(self, unmanaged=False):
        return GitHubDynamicDependency(
            github="https://github.com/SFDO-Tooling/TwoGPRepo",
            unmanaged=unmanaged,
        )

    def test_can_resolve__no_feature_branch(self):
        # On the default branch, with no active feature branch overlay, the
        # resolver short-circuits cleanly.
        context = self._make_context(active=None, repo_branch="main")
        resolver = GitHubFeatureBranchTagResolver()
        assert not resolver.can_resolve(self._dep(), context)

    def test_can_resolve__repo_branch_with_prefix(self):
        context = self._make_context(active=None, repo_branch="feature/widget")
        resolver = GitHubFeatureBranchTagResolver()
        assert resolver.can_resolve(self._dep(), context)

    def test_can_resolve__arbitrary_non_default_branch(self):
        # Any non-default branch (not only the feature/ prefix) is treated as a
        # candidate feature/epic branch, so an epic branch is picked up.
        context = self._make_context(active=None, repo_branch="epic/new-billing")
        resolver = GitHubFeatureBranchTagResolver()
        assert resolver.can_resolve(self._dep(), context)

    def test_can_resolve__active_feature_branch_lookup(self):
        # The active_feature_branch overlay takes priority even when repo_branch
        # is the default branch.
        context = self._make_context(active="feature/gadget", repo_branch="main")
        resolver = GitHubFeatureBranchTagResolver()
        assert resolver.can_resolve(self._dep(), context)

    @mock.patch("cumulusci.core.dependencies.resolvers.get_package_data")
    @mock.patch("cumulusci.core.dependencies.resolvers.get_remote_project_config")
    @mock.patch("cumulusci.core.dependencies.resolvers.get_tag_refs_for_prefix")
    @mock.patch("cumulusci.core.dependencies.resolvers.get_repo")
    def test_resolve__highest_version(
        self, get_repo, get_tag_refs, get_remote_config, get_package_data
    ):
        context = self._make_context(active=None, repo_branch="feature/widget")
        repo = mock.Mock()
        get_repo.return_value = repo

        ref1 = mock.Mock()
        ref1.object.sha = "sha1"
        ref2 = mock.Mock()
        ref2.object.sha = "sha2"
        ref10 = mock.Mock()
        ref10.object.sha = "sha10"
        # Build 10 must beat build 2 (integer sort, not string).
        get_tag_refs.return_value = [
            ("feature/widget/2.5.0.1", ref1),
            ("feature/widget/2.5.0.2", ref2),
            ("feature/widget/2.5.0.10", ref10),
        ]

        tag = mock.Mock()
        tag.object.sha = "commit_sha_10"
        tag.message = "version_id: 04t000000000010\n\npackage_type: 2GP"
        repo.tag.return_value = tag

        get_remote_config.return_value = mock.Mock()
        get_package_data.return_value = ("MyPackage", "ns")

        resolver = GitHubFeatureBranchTagResolver()
        result = resolver.resolve(self._dep(), context)

        # Winning tag is the build-10 tag.
        repo.tag.assert_called_once_with("sha10")
        assert result == (
            "commit_sha_10",
            PackageVersionIdDependency(
                version_id="04t000000000010",
                version_number="2.5.0.10",
                package_name="MyPackage",
            ),
        )

    @mock.patch("cumulusci.core.dependencies.resolvers.get_tag_refs_for_prefix")
    @mock.patch("cumulusci.core.dependencies.resolvers.get_repo")
    def test_resolve__uses_active_feature_branch_prefix(self, get_repo, get_tag_refs):
        context = self._make_context(active="feature/gadget", repo_branch="main")
        get_repo.return_value = mock.Mock()
        get_tag_refs.return_value = []

        resolver = GitHubFeatureBranchTagResolver()
        assert resolver.resolve(self._dep(), context) == (None, None)
        get_tag_refs.assert_called_once_with(get_repo.return_value, "feature/gadget/")

    @mock.patch("cumulusci.core.dependencies.resolvers.get_package_data")
    @mock.patch("cumulusci.core.dependencies.resolvers.get_remote_project_config")
    @mock.patch("cumulusci.core.dependencies.resolvers.get_tag_refs_for_prefix")
    @mock.patch("cumulusci.core.dependencies.resolvers.get_repo")
    def test_resolve__unmanaged_returns_no_package_dependency(
        self, get_repo, get_tag_refs, get_remote_config, get_package_data
    ):
        # An explicitly unmanaged dependency resolves to the tagged commit with
        # no package dependency, so it deploys as unmanaged metadata.
        context = self._make_context(active=None, repo_branch="feature/widget")
        repo = mock.Mock()
        get_repo.return_value = repo
        ref = mock.Mock()
        ref.object.sha = "sha1"
        get_tag_refs.return_value = [("feature/widget/2.5.0.1", ref)]
        tag = mock.Mock()
        tag.object.sha = "commit_sha"
        tag.message = "version_id: 04t000000000001\n\npackage_type: 2GP"
        repo.tag.return_value = tag

        resolver = GitHubFeatureBranchTagResolver()
        result = resolver.resolve(self._dep(unmanaged=True), context)

        assert result == ("commit_sha", None)
        # The package config is never fetched when installing unmanaged.
        get_remote_config.assert_not_called()

    @mock.patch("cumulusci.core.dependencies.resolvers.get_tag_refs_for_prefix")
    @mock.patch("cumulusci.core.dependencies.resolvers.get_repo")
    def test_resolve__no_tags(self, get_repo, get_tag_refs):
        context = self._make_context(active=None, repo_branch="feature/widget")
        get_repo.return_value = mock.Mock()
        get_tag_refs.return_value = []

        resolver = GitHubFeatureBranchTagResolver()
        assert resolver.resolve(self._dep(), context) == (None, None)

    @mock.patch("cumulusci.core.dependencies.resolvers.get_tag_refs_for_prefix")
    @mock.patch("cumulusci.core.dependencies.resolvers.get_repo")
    def test_resolve__no_version_id_in_tag(self, get_repo, get_tag_refs):
        context = self._make_context(active=None, repo_branch="feature/widget")
        repo = mock.Mock()
        get_repo.return_value = repo
        ref = mock.Mock()
        ref.object.sha = "sha1"
        get_tag_refs.return_value = [("feature/widget/2.5.0.1", ref)]
        tag = mock.Mock()
        tag.object.sha = "commit_sha"
        tag.message = "package_type: 2GP"  # no version_id
        repo.tag.return_value = tag

        resolver = GitHubFeatureBranchTagResolver()
        assert resolver.resolve(self._dep(), context) == (None, None)


class TestGitHubUnmanagedHeadResolver:
    def test_unmanaged_head_resolver(self, project_config):
        dep = GitHubDynamicDependency(
            github="https://github.com/SFDO-Tooling/ReleasesRepo"
        )
        resolver = GitHubUnmanagedHeadResolver()

        assert resolver.can_resolve(dep, project_config)

        assert resolver.resolve(dep, project_config) == ("commit_sha", None)


class ConcreteGitHubReleaseBranchResolver(AbstractGitHubReleaseBranchResolver):
    def resolve(
        self, dep: GitHubDynamicDependency, context: BaseProjectConfig
    ) -> Tuple[Optional[str], Optional[StaticDependency]]:
        return (None, None)


class TestGitHubReleaseBranchResolver:
    def test_is_valid_repo_context(self):
        pc = BaseProjectConfig(UniversalConfig())

        pc.repo_info["branch"] = "feature/232__test"
        pc.project__git["prefix_feature"] = "feature/"

        assert ConcreteGitHubReleaseBranchResolver().is_valid_repo_context(pc)

        pc.repo_info["branch"] = "main"
        assert not ConcreteGitHubReleaseBranchResolver().is_valid_repo_context(pc)

    def test_can_resolve(self):
        pc = BaseProjectConfig(UniversalConfig())

        pc.repo_info["branch"] = "feature/232__test"
        pc.project__git["prefix_feature"] = "feature/"

        gh = ConcreteGitHubReleaseBranchResolver()

        assert gh.can_resolve(
            GitHubDynamicDependency(github="https://github.com/SFDO-Tooling/Test"),
            pc,
        )

        assert not gh.can_resolve(ConcreteDynamicDependency(), pc)

    def test_get_release_id(self):
        pc = BaseProjectConfig(UniversalConfig())
        pc.repo_info["branch"] = "feature/232__test"
        pc.project__git["prefix_feature"] = "feature/"

        assert get_release_id(pc) == 232

    def test_get_release_id__not_release_branch(self):
        pc = BaseProjectConfig(UniversalConfig())
        with mock.patch.object(
            BaseProjectConfig, "repo_branch", new_callable=mock.PropertyMock
        ) as repo_branch:
            repo_branch.return_value = None

            with pytest.raises(DependencyResolutionError) as e:
                get_release_id(pc)

            assert "Cannot get current branch" in str(e)

    def test_get_release_id__no_git_data(self):
        pc = BaseProjectConfig(UniversalConfig())
        with mock.patch.object(
            BaseProjectConfig, "repo_branch", new_callable=mock.PropertyMock
        ) as repo_branch:
            repo_branch.return_value = "feature/test"
            pc.project__git["prefix_feature"] = "feature/"

            with pytest.raises(DependencyResolutionError) as e:
                get_release_id(pc)

            assert "Cannot get current release identifier" in str(e)

    def test_locate_commit_status_package_id__not_found_with_parent(self, github):
        repo = github.repository("SFDO-Tooling", "TwoGPMissingRepo")
        assert locate_commit_status_package_id(
            repo, repo.branch("feature/232"), "Build Feature Test Package"
        ) == (None, None)


class TestGitHubReleaseBranchCommitStatusResolver:
    def test_2gp_release_branch_resolver(self, project_config):
        project_config.repo_branch = "feature/232__test"
        project_config.project__git__prefix_feature = "feature/"

        resolver = GitHubReleaseBranchCommitStatusResolver()
        dep = GitHubDynamicDependency(
            github="https://github.com/SFDO-Tooling/TwoGPRepo"
        )

        assert resolver.can_resolve(dep, project_config)

        assert resolver.resolve(dep, project_config) == (
            "parent_sha",
            PackageVersionIdDependency(
                version_id="04t000000000000", package_name="CumulusCI-2GP-Test"
            ),
        )

    def test_commit_status_not_found(self, project_config):
        project_config.repo_branch = "feature/232__test"
        project_config.project__git__prefix_feature = "feature/"

        resolver = GitHubReleaseBranchCommitStatusResolver()
        dep = GitHubDynamicDependency(
            github="https://github.com/SFDO-Tooling/TwoGPMissingRepo"
        )

        assert resolver.can_resolve(dep, project_config)
        assert resolver.resolve(dep, project_config) == (None, None)

    def test_repo_not_found(self, project_config):
        project_config.repo_branch = "feature/232__test"
        project_config.project__git__prefix_feature = "feature/"

        resolver = GitHubReleaseBranchCommitStatusResolver()
        dep = GitHubDynamicDependency(
            github="https://github.com/SFDO-Tooling/NonexistentRepo"
        )

        project_config.get_repo_from_url = mock.Mock(return_value=None)

        with pytest.raises(DependencyResolutionError) as exc:
            resolver.resolve(dep, project_config)

        assert "Unable to access GitHub" in str(exc)

    @mock.patch("cumulusci.core.dependencies.resolvers.find_repo_feature_prefix")
    def test_unable_locate_feature_prefix(
        self, find_repo_feature_prefix_mock, project_config
    ):
        find_repo_feature_prefix_mock.side_effect = NotFoundError
        project_config.repo_branch = "feature/232__test"
        project_config.project__git__prefix_feature = "feature/"

        resolver = GitHubReleaseBranchCommitStatusResolver()
        dep = GitHubDynamicDependency(
            github="https://github.com/SFDO-Tooling/TwoGPRepo"
        )
        assert resolver.resolve(dep, project_config) == (None, None)

    def test_branch_not_found(self, project_config):
        project_config.repo_branch = "feature/290__test"
        project_config.project__git__prefix_feature = "feature/"

        resolver = GitHubReleaseBranchCommitStatusResolver()
        dep = GitHubDynamicDependency(
            github="https://github.com/SFDO-Tooling/TwoGPRepo"
        )

        assert resolver.resolve(dep, project_config) == (None, None)


class TestGitHubExactMatch2GPResolver:
    def test_exact_branch_resolver(self, project_config):
        project_config.repo_branch = "feature/232__test"
        project_config.project__git__prefix_feature = "feature/"

        resolver = GitHubExactMatch2GPResolver()
        dep = GitHubDynamicDependency(
            github="https://github.com/SFDO-Tooling/TwoGPRepo"
        )

        assert resolver.can_resolve(dep, project_config)
        assert resolver.resolve(dep, project_config) == (
            "feature/232__test_sha",
            PackageVersionIdDependency(
                version_id="04t000000000001", package_name="CumulusCI-2GP-Test"
            ),
        )

    def test_repo_not_found(self, project_config):
        project_config.repo_branch = "feature/232__test"
        project_config.project__git__prefix_feature = "feature/"

        resolver = GitHubExactMatch2GPResolver()
        dep = GitHubDynamicDependency(
            github="https://github.com/SFDO-Tooling/NonexistentRepo"
        )

        project_config.get_repo_from_url = mock.Mock(return_value=None)

        with pytest.raises(DependencyResolutionError) as exc:
            resolver.resolve(dep, project_config)

        assert "Unable to access GitHub" in str(exc)

    @mock.patch("cumulusci.core.dependencies.resolvers.find_repo_feature_prefix")
    def test_unable_locate_feature_prefix(
        self, find_repo_feature_prefix_mock, project_config
    ):
        find_repo_feature_prefix_mock.side_effect = NotFoundError
        project_config.repo_branch = "feature/232__test"
        project_config.project__git__prefix_feature = "feature/"

        resolver = GitHubExactMatch2GPResolver()
        dep = GitHubDynamicDependency(
            github="https://github.com/SFDO-Tooling/TwoGPRepo"
        )
        assert resolver.resolve(dep, project_config) == (None, None)

    def test_branch_not_found(self, project_config):
        project_config.repo_branch = "feature/290__test"
        project_config.project__git__prefix_feature = "feature/"

        resolver = GitHubExactMatch2GPResolver()
        dep = GitHubDynamicDependency(
            github="https://github.com/SFDO-Tooling/TwoGPRepo"
        )

        assert resolver.resolve(dep, project_config) == (None, None)

    def test_commit_status_not_found(self, project_config):
        project_config.repo_branch = "feature/232"
        project_config.project__git__prefix_feature = "feature/"

        resolver = GitHubExactMatch2GPResolver()
        dep = GitHubDynamicDependency(
            github="https://github.com/SFDO-Tooling/TwoGPMissingRepo"
        )

        assert resolver.can_resolve(dep, project_config)
        assert resolver.resolve(dep, project_config) == (None, None)


class TestGitHubDefaultBranch2GPResolver:
    def test_default_branch_resolver(self, project_config):
        project_config.repo_branch = "feature/299__test"
        project_config.project__git__prefix_feature = "feature/"

        resolver = GitHubDefaultBranch2GPResolver()
        dep = GitHubDynamicDependency(
            github="https://github.com/SFDO-Tooling/TwoGPRepo"
        )

        assert resolver.can_resolve(dep, project_config)
        assert resolver.resolve(dep, project_config) == (
            "main_sha",
            PackageVersionIdDependency(
                version_id="04t000000000005", package_name="CumulusCI-2GP-Test"
            ),
        )

    def test_commit_status_not_found(self, project_config):
        project_config.repo_branch = "feature/299"
        project_config.project__git__prefix_feature = "feature/"

        resolver = GitHubDefaultBranch2GPResolver()
        dep = GitHubDynamicDependency(
            github="https://github.com/SFDO-Tooling/TwoGPMissingRepo"
        )

        assert resolver.can_resolve(dep, project_config)
        assert resolver.resolve(dep, project_config) == (None, None)


class TestResolverAccess:
    def test_get_resolver(self):
        assert isinstance(
            get_resolver(
                DependencyResolutionStrategy.STATIC_TAG_REFERENCE,
                GitHubDynamicDependency(github="https://github.com/SFDO-Tooling/Test"),
            ),
            GitHubTagResolver,
        )

    def test_get_resolver_stack__indirect(self):
        pc = BaseProjectConfig(UniversalConfig())

        strategy = get_resolver_stack(pc, "production")
        assert DependencyResolutionStrategy.RELEASE_TAG in strategy
        assert DependencyResolutionStrategy.BETA_RELEASE_TAG not in strategy

    def test_get_resolver_stack__customized_indirect(self):
        pc = BaseProjectConfig(UniversalConfig())

        pc.project__dependency_resolutions["preproduction"] = "include_beta"
        strategy = get_resolver_stack(pc, "preproduction")
        assert DependencyResolutionStrategy.BETA_RELEASE_TAG in strategy

    def test_get_resolver_stack__direct(self):
        pc = BaseProjectConfig(UniversalConfig())

        strategy = get_resolver_stack(pc, "commit_status")
        assert DependencyResolutionStrategy.COMMIT_STATUS_RELEASE_BRANCH in strategy

    def test_get_resolver_stack__fail(self):
        pc = BaseProjectConfig(UniversalConfig())

        with pytest.raises(CumulusCIException) as e:
            get_resolver_stack(pc, "bogus")

        assert "not found" in str(e)


class TestStaticDependencyResolution:
    def test_get_static_dependencies(self, project_config):
        gh = GitHubDynamicDependency(github="https://github.com/SFDO-Tooling/RootRepo")

        assert get_static_dependencies(
            project_config,
            dependencies=[gh],
            strategies=[DependencyResolutionStrategy.RELEASE_TAG],
        ) == [
            UnmanagedGitHubRefDependency(
                github="https://github.com/SFDO-Tooling/DependencyRepo",
                subfolder="unpackaged/pre/top",
                unmanaged=True,
                ref="tag_sha",
            ),
            PackageNamespaceVersionDependency(
                namespace="foo",
                version="1.1",
                package_name="DependencyRepo",
                password_env_name="DEP_PW",
            ),
            UnmanagedGitHubRefDependency(
                github="https://github.com/SFDO-Tooling/DependencyRepo",
                subfolder="unpackaged/post/top",
                unmanaged=False,
                ref="tag_sha",
                namespace_inject="foo",
            ),
            UnmanagedGitHubRefDependency(
                github="https://github.com/SFDO-Tooling/RootRepo",
                subfolder="unpackaged/pre/first",
                unmanaged=True,
                ref="tag_sha",
            ),
            UnmanagedGitHubRefDependency(
                github="https://github.com/SFDO-Tooling/RootRepo",
                subfolder="unpackaged/pre/second",
                unmanaged=True,
                ref="tag_sha",
            ),
            PackageNamespaceVersionDependency(
                namespace="bar", version="2.0", package_name="RootRepo"
            ),
            UnmanagedGitHubRefDependency(
                github="https://github.com/SFDO-Tooling/RootRepo",
                subfolder="unpackaged/post/first",
                unmanaged=False,
                ref="tag_sha",
                namespace_inject="bar",
            ),
        ]

    def test_get_static_dependencies__pins(self, project_config):
        gh = GitHubDynamicDependency(github="https://github.com/SFDO-Tooling/RootRepo")

        tag = mock.Mock()
        tag.return_value.object.sha = "tag_sha"
        tag.return_value.message = """
package_type: 1GP

version_id: 04t000000000000"""
        project_config.get_repo_from_url(
            "https://github.com/SFDO-Tooling/RootRepo"
        ).tag = tag

        project_config.get_repo_from_url(
            "https://github.com/SFDO-Tooling/DependencyRepo"
        ).tag = tag

        # Add a pin for the direct dependency and a transitive dependency
        pins = [
            GitHubDependencyPin(
                github="https://github.com/SFDO-Tooling/DependencyRepo",
                tag="release/1.0",
            ),
            GitHubDependencyPin(
                github="https://github.com/SFDO-Tooling/RootRepo", tag="release/1.5"
            ),
        ]

        assert pins[1].can_pin(gh)

        deps = get_static_dependencies(
            project_config,
            dependencies=[gh],
            strategies=[DependencyResolutionStrategy.RELEASE_TAG],
            pins=pins,
        )

        assert deps == [
            UnmanagedGitHubRefDependency(
                github="https://github.com/SFDO-Tooling/DependencyRepo",
                subfolder="unpackaged/pre/top",
                unmanaged=True,
                ref="tag_sha",
            ),
            PackageNamespaceVersionDependency(
                namespace="foo",
                version="1.0",  # from the pinned tag
                package_name="DependencyRepo",
                version_id="04t000000000000",
            ),
            UnmanagedGitHubRefDependency(
                github="https://github.com/SFDO-Tooling/DependencyRepo",
                subfolder="unpackaged/post/top",
                unmanaged=False,
                ref="tag_sha",
                namespace_inject="foo",
            ),
            UnmanagedGitHubRefDependency(
                github="https://github.com/SFDO-Tooling/RootRepo",
                subfolder="unpackaged/pre/first",
                unmanaged=True,
                ref="tag_sha",
            ),
            UnmanagedGitHubRefDependency(
                github="https://github.com/SFDO-Tooling/RootRepo",
                subfolder="unpackaged/pre/second",
                unmanaged=True,
                ref="tag_sha",
            ),
            PackageNamespaceVersionDependency(
                namespace="bar",
                version="1.5",  # From pinned tag
                package_name="RootRepo",
                version_id="04t000000000000",
            ),
            UnmanagedGitHubRefDependency(
                github="https://github.com/SFDO-Tooling/RootRepo",
                subfolder="unpackaged/post/first",
                unmanaged=False,
                ref="tag_sha",
                namespace_inject="bar",
            ),
        ]

    def test_get_static_dependencies__conflicting_pin(self, project_config):
        gh = GitHubDynamicDependency(
            github="https://github.com/SFDO-Tooling/RootRepo", tag="release/foo"
        )

        # Add a pin for the direct dependency that conflicts
        pins = [
            GitHubDependencyPin(
                github="https://github.com/SFDO-Tooling/RootRepo", tag="release/1.5"
            ),
        ]

        assert pins[0].can_pin(gh)
        with pytest.raises(
            DependencyResolutionError, match="dependency already has a tag specified"
        ):
            get_static_dependencies(
                project_config,
                dependencies=[gh],
                strategies=[DependencyResolutionStrategy.RELEASE_TAG],
                pins=pins,
            )

    def test_get_static_dependencies__ignore_namespace(self, project_config):
        gh = GitHubDynamicDependency(github="https://github.com/SFDO-Tooling/RootRepo")

        assert get_static_dependencies(
            project_config,
            dependencies=[gh],
            strategies=[DependencyResolutionStrategy.RELEASE_TAG],
            filter_function=dependency_filter_ignore_deps([{"namespace": "foo"}]),
        ) == [
            UnmanagedGitHubRefDependency(
                github="https://github.com/SFDO-Tooling/DependencyRepo",
                subfolder="unpackaged/pre/top",
                unmanaged=True,
                ref="tag_sha",
            ),
            UnmanagedGitHubRefDependency(
                github="https://github.com/SFDO-Tooling/DependencyRepo",
                subfolder="unpackaged/post/top",
                unmanaged=False,
                ref="tag_sha",
                namespace_inject="foo",
            ),
            UnmanagedGitHubRefDependency(
                github="https://github.com/SFDO-Tooling/RootRepo",
                subfolder="unpackaged/pre/first",
                unmanaged=True,
                ref="tag_sha",
            ),
            UnmanagedGitHubRefDependency(
                github="https://github.com/SFDO-Tooling/RootRepo",
                subfolder="unpackaged/pre/second",
                unmanaged=True,
                ref="tag_sha",
            ),
            PackageNamespaceVersionDependency(
                namespace="bar", version="2.0", package_name="RootRepo"
            ),
            UnmanagedGitHubRefDependency(
                github="https://github.com/SFDO-Tooling/RootRepo",
                subfolder="unpackaged/post/first",
                unmanaged=False,
                ref="tag_sha",
                namespace_inject="bar",
            ),
        ]

    def test_get_static_dependencies__ignore_github(self, project_config):
        gh = GitHubDynamicDependency(github="https://github.com/SFDO-Tooling/RootRepo")

        assert get_static_dependencies(
            project_config,
            dependencies=[gh],
            strategies=[DependencyResolutionStrategy.RELEASE_TAG],
            filter_function=dependency_filter_ignore_deps(
                [{"github": "https://github.com/SFDO-Tooling/DependencyRepo"}]
            ),
        ) == [
            UnmanagedGitHubRefDependency(
                github="https://github.com/SFDO-Tooling/RootRepo",
                subfolder="unpackaged/pre/first",
                unmanaged=True,
                ref="tag_sha",
            ),
            UnmanagedGitHubRefDependency(
                github="https://github.com/SFDO-Tooling/RootRepo",
                subfolder="unpackaged/pre/second",
                unmanaged=True,
                ref="tag_sha",
            ),
            PackageNamespaceVersionDependency(
                namespace="bar", version="2.0", package_name="RootRepo"
            ),
            UnmanagedGitHubRefDependency(
                github="https://github.com/SFDO-Tooling/RootRepo",
                subfolder="unpackaged/post/first",
                unmanaged=False,
                ref="tag_sha",
                namespace_inject="bar",
            ),
        ]

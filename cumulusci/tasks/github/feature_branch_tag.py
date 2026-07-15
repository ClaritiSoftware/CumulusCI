import time
from datetime import datetime

import github3.exceptions

from cumulusci.core.exceptions import GithubException, TaskOptionsError
from cumulusci.tasks.github.base import BaseGithubTask


class CreateFeatureBranchTag(BaseGithubTask):
    """Records a feature-branch 2GP beta as an annotated git tag ONLY.

    Unlike ``github_release`` (CreateRelease), this task never creates a GitHub
    Release object. Feature-branch versions must not become Releases, or they
    would be surfaced as the global "latest beta" by Release-based resolvers
    such as ``GitHubBetaReleaseTagResolver``. Annotated git tags are read back
    through the git refs API by ``GitHubFeatureBranchTagResolver``.

    The version_id (04t) is embedded in the tag message in the same format used
    by CreateRelease so it round-trips through ``get_version_id_from_tag``.
    """

    task_options = {
        "version": {
            "description": "The 2GP package version number. Ex: 2.5.0.1",
            "required": True,
        },
        "version_id": {
            "description": "The SubscriberPackageVersionId (04t) associated with this version.",
            "required": True,
        },
        "commit": {
            "description": (
                "Override the commit used to create the tag. "
                "Defaults to the current local HEAD commit"
            )
        },
        "package_type": {
            "description": "The package type of the project. Defaults to 2GP.",
        },
        "branch": {
            "description": "The feature branch to tag. Defaults to the project's current repo branch."
        },
        "tag_prefix": {
            "description": "The tag prefix (including trailing slash) to use for the tag. "
            "Defaults to `<branch>/`."
        },
    }

    def _init_options(self, kwargs):
        super()._init_options(kwargs)

        self.commit = self.options.get("commit", self.project_config.repo_commit)
        if not self.commit:
            message = "Could not detect the current commit from the local repo"
            self.logger.error(message)
            raise GithubException(message)
        if len(self.commit) != 40:
            raise TaskOptionsError("The commit option must be exactly 40 characters.")

    def _run_task(self):
        repo = self.get_repo()
        version = self.options["version"]
        package_type = self.options.get("package_type") or "2GP"

        branch = self.options.get("branch") or self.project_config.repo_branch
        if not branch:
            raise TaskOptionsError(
                "Could not detect the current branch; specify the `branch` option."
            )
        prefix = self.options.get("tag_prefix") or f"{branch}/"
        tag_name = self.project_config.get_tag_for_version(prefix, version)

        # Idempotency: no-op if the tag already exists.
        try:
            repo.ref(f"tags/{tag_name}")
        except github3.exceptions.NotFoundError:
            pass
        else:
            self.logger.info(f"Tag {tag_name} already exists; skipping.")
            self.return_values = {"tag_name": tag_name}
            return

        # Embed version_id in the tag message in the same format CreateRelease
        # uses so it round-trips through get_version_id_from_tag.
        message = f"Feature branch package version {version}"
        message += f"\n\nversion_id: {self.options['version_id']}"
        message += f"\n\npackage_type: {package_type}"

        # Create the annotated tag. lightweight=False creates both the tag object
        # and the refs/tags/... ref in one call. We intentionally do NOT create a
        # GitHub Release.
        repo.create_tag(
            tag=tag_name,
            message=message,
            sha=self.commit,
            obj_type="commit",
            tagger={
                "name": self.github_config.username,
                "email": self.github_config.email,
                "date": f"{datetime.utcnow().isoformat()}Z",
            },
            lightweight=False,
        )

        # Sleep for GitHub to catch up with the fact that the tag exists.
        time.sleep(3)

        self.logger.info(f"Created annotated tag {tag_name} (no GitHub Release).")
        self.return_values = {"tag_name": tag_name}
        return self.return_values

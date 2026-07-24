import json
from unittest import mock

import responses

from cumulusci.core.config import ServiceConfig, TaskConfig
from cumulusci.tasks.github.feature_branch_tag import CreateFeatureBranchTag
from cumulusci.tasks.github.tests.util_github_api import GithubApiTestMixin
from cumulusci.tests.util import create_project_config


class TestCreateFeatureBranchTag(GithubApiTestMixin):
    def setup_method(self):
        self.repo_owner = "TestOwner"
        self.repo_name = "TestRepo"
        self.commit_sha = "21e04cfe480f5293e2f7103eee8a5cbdb94f7982"
        self.repo_api_url = "https://api.github.com/repos/{}/{}".format(
            self.repo_owner, self.repo_name
        )
        self.project_config = create_project_config(self.repo_name, self.repo_owner)
        self.project_config.keychain.set_service(
            "github",
            "test_alias",
            ServiceConfig(
                {
                    "username": "TestUser",
                    "token": "TestPass",
                    "email": "testuser@testdomain.com",
                }
            ),
        )

    def _task(self, options=None):
        opts = {
            "version": "2.5.0.1",
            "version_id": "04t000000000001",
            "commit": self.commit_sha,
            "branch": "feature/widget",
        }
        opts.update(options or {})
        return CreateFeatureBranchTag(
            self.project_config, TaskConfig({"options": opts})
        )

    @responses.activate
    @mock.patch("cumulusci.tasks.github.feature_branch_tag.time.sleep")
    def test_run_task__creates_annotated_tag(self, sleep):
        expected_tag_name = "feature/widget/2.5.0.1"
        responses.add(
            method=responses.GET,
            url=self.repo_api_url,
            json=self._get_expected_repo(owner=self.repo_owner, name=self.repo_name),
        )
        # Idempotency check: ref does not yet exist.
        responses.add(
            responses.GET,
            self.repo_api_url + f"/git/ref/tags/{expected_tag_name}",
            status=404,
        )
        responses.add(
            responses.POST,
            self.repo_api_url + "/git/tags",
            json=self._get_expected_tag(expected_tag_name, self.commit_sha),
            status=201,
        )
        responses.add(
            responses.POST, self.repo_api_url + "/git/refs", json={}, status=201
        )

        task = self._task()
        task()

        assert task.return_values["tag_name"] == expected_tag_name

        # An annotated tag object was created (POST /git/tags) with the
        # version_id embedded in the message so get_version_id_from_tag can read it.
        tag_calls = [c for c in responses.calls if c.request.url.endswith("/git/tags")]
        assert len(tag_calls) == 1
        body = json.loads(tag_calls[0].request.body)
        assert body["tag"] == expected_tag_name
        assert "version_id: 04t000000000001" in body["message"]
        assert "package_type: 2GP" in body["message"]
        assert body["object"] == self.commit_sha
        assert body["type"] == "commit"
        assert body["tagger"]["name"] == "TestUser"

        # The ref was created (lightweight=False creates both objects).
        ref_calls = [c for c in responses.calls if c.request.url.endswith("/git/refs")]
        assert len(ref_calls) == 1

        # No GitHub Release was created.
        release_calls = [
            c for c in responses.calls if c.request.url.endswith("/releases")
        ]
        assert release_calls == []

        sleep.assert_called_once()

    @responses.activate
    @mock.patch("cumulusci.tasks.github.feature_branch_tag.time.sleep")
    def test_run_task__idempotent_when_tag_exists(self, sleep):
        expected_tag_name = "feature/widget/2.5.0.1"
        responses.add(
            method=responses.GET,
            url=self.repo_api_url,
            json=self._get_expected_repo(owner=self.repo_owner, name=self.repo_name),
        )
        # Ref already exists.
        responses.add(
            responses.GET,
            self.repo_api_url + f"/git/ref/tags/{expected_tag_name}",
            json={
                "object": {"sha": "SHA", "url": "", "type": "tag"},
                "url": "",
                "ref": f"refs/tags/{expected_tag_name}",
            },
            status=200,
        )

        task = self._task()
        task()

        assert task.return_values["tag_name"] == expected_tag_name
        # No tag/ref/release POSTs were made.
        post_calls = [c for c in responses.calls if c.request.method == "POST"]
        assert post_calls == []
        sleep.assert_not_called()

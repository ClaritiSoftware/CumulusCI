from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from cumulusci.cli.org import org


class FakeRuntime:
    def __init__(self):
        self.project_config = SimpleNamespace(repo_root="/tmp")

    def _load_keychain(self):
        # Tests bypass actual keychain loading.
        pass

def test_org_import_rejects_username_and_pool_id(tmp_path):
    runner = CliRunner()
    runtime = FakeRuntime()
    runtime.project_config.repo_root = str(tmp_path)

    result = runner.invoke(
        org,
        ["import", "example@force.com", "--org", "alias", "--pool-id", "Pool42"],
        obj=runtime,
    )

    assert result.exit_code != 0
    assert "Provide either USERNAME_OR_ALIAS" in result.output
    assert "--pool-id" in result.output

import contextlib
import io
import os
import shutil
import sys
import tempfile
from pathlib import Path
from unittest import mock

import click
import pytest
from packaging import version
from requests.exceptions import ConnectionError
from rich.console import Console

import cumulusci
from cumulusci.cli import cci
from cumulusci.cli.tests.utils import run_click_command
from cumulusci.cli.utils import get_installed_version
from cumulusci.core.config import BaseProjectConfig
from cumulusci.core.exceptions import CumulusCIException
from cumulusci.utils import temporary_dir

MagicMock = mock.MagicMock()
CONSOLE = mock.Mock()


@pytest.fixture(autouse=True)
def env_config():
    config = {
        "global_tempdir": tempfile.gettempdir(),
        "tempdir": tempfile.mkdtemp(),
        "environ_mock": mock.patch.dict(
            os.environ, {"HOME": tempfile.mkdtemp(), "CUMULUSCI_KEY": ""}
        ),
    }
    # setup
    config["environ_mock"].start()
    assert config["global_tempdir"] in os.environ["HOME"]
    yield config
    # tear down
    assert config["global_tempdir"] in os.environ["HOME"]
    config["environ_mock"].stop()
    shutil.rmtree(config["tempdir"])


@mock.patch("cumulusci.cli.cci.tee_stdout_stderr")
@mock.patch("cumulusci.cli.cci.get_tempfile_logger")
@mock.patch("cumulusci.cli.cci.init_logger")
@mock.patch("cumulusci.cli.cci.check_latest_version")
@mock.patch("cumulusci.cli.cci.CliRuntime")
@mock.patch("cumulusci.cli.cci.cli")
def test_main(
    cli,
    CliRuntime,
    check_latest_version,
    init_logger,
    get_tempfile_logger,
    tee,
):
    get_tempfile_logger.return_value = mock.Mock(), "tempfile.log"
    cci.main()

    check_latest_version.assert_called_once()
    init_logger.assert_called_once()
    CliRuntime.assert_called_once()
    cli.assert_called_once()
    tee.assert_called_once()


@mock.patch("cumulusci.cli.cci.tee_stdout_stderr")
@mock.patch("cumulusci.cli.cci.get_tempfile_logger")
@mock.patch("cumulusci.cli.cci.init_logger")
@mock.patch("cumulusci.cli.cci.check_latest_version")
@mock.patch("cumulusci.cli.cci.CliRuntime")
@mock.patch("cumulusci.cli.cci.cli")
@mock.patch("pdb.post_mortem")
@mock.patch("sys.exit")
def test_main__debug(
    sys_exit,
    post_mortem,
    cli,
    CliRuntime,
    check_latest_version,
    init_logger,
    get_tempfile_logger,
    tee,
):
    cli.side_effect = Exception
    get_tempfile_logger.return_value = (mock.Mock(), "tempfile.log")

    cci.main(["cci", "--debug"])

    check_latest_version.assert_called_once()
    init_logger.assert_called_once_with(debug=True)
    CliRuntime.assert_called_once()
    cli.assert_called_once()
    post_mortem.assert_called_once()
    sys_exit.assert_called_once_with(1)
    get_tempfile_logger.assert_called_once()
    tee.assert_called_once()


@mock.patch("cumulusci.cli.cci.tee_stdout_stderr")
@mock.patch("cumulusci.cli.cci.get_tempfile_logger")
@mock.patch("cumulusci.cli.cci.init_logger")
@mock.patch("cumulusci.cli.cci.check_latest_version")
@mock.patch("cumulusci.cli.cci.CliRuntime")
@mock.patch("cumulusci.cli.cci.cli")
@mock.patch("pdb.post_mortem")
def test_main__cci_show_stacktraces(
    post_mortem,
    cli,
    CliRuntime,
    check_latest_version,
    init_logger,
    get_tempfile_logger,
    tee,
    capsys,
):
    runtime = mock.Mock()
    runtime.universal_config.cli__show_stacktraces = True
    CliRuntime.return_value = runtime
    cli.side_effect = Exception
    get_tempfile_logger.return_value = (mock.Mock(), "tempfile.log")

    with pytest.raises(SystemExit):
        cci.main(["cci"])

    check_latest_version.assert_called_once()
    init_logger.assert_called_once_with(debug=False)
    CliRuntime.assert_called_once()
    cli.assert_called_once()
    post_mortem.assert_not_called()
    captured = capsys.readouterr()
    assert "Traceback (most recent call last)" in captured.err


@mock.patch("cumulusci.cli.cci.tee_stdout_stderr")
@mock.patch("cumulusci.cli.cci.get_tempfile_logger")
@mock.patch("cumulusci.cli.cci.init_logger")
@mock.patch("cumulusci.cli.cci.cli")
@mock.patch("sys.exit")
def test_main__abort(
    sys_exit, cli, init_logger, get_tempfile_logger, tee_stdout_stderr
):
    get_tempfile_logger.return_value = (mock.Mock(), "tempfile.log")
    cli.side_effect = click.Abort
    cci.main(["cci"])
    cli.assert_called_once()
    sys_exit.assert_called_once_with(1)


@mock.patch("cumulusci.cli.cci.tee_stdout_stderr")
@mock.patch("cumulusci.cli.cci.get_tempfile_logger")
@mock.patch("cumulusci.cli.cci.init_logger")
@mock.patch("cumulusci.cli.cci.check_latest_version")
@mock.patch("cumulusci.cli.cci.CliRuntime")
@mock.patch("cumulusci.cli.cci.cli")
@mock.patch("pdb.post_mortem")
@mock.patch("sys.exit")
def test_main__error(
    sys_exit,
    post_mortem,
    cli,
    CliRuntime,
    check_latest_version,
    init_logger,
    get_tempfile_logger,
    tee,
):
    runtime = mock.Mock()
    runtime.universal_config.cli__show_stacktraces = False
    CliRuntime.return_value = runtime

    cli.side_effect = Exception
    get_tempfile_logger.return_value = mock.Mock(), "tempfile.log"

    cci.main(["cci", "org", "info"])

    check_latest_version.assert_called_once()
    init_logger.assert_called_once_with(debug=False)
    CliRuntime.assert_called_once()
    cli.assert_called_once()
    post_mortem.call_count == 0
    sys_exit.assert_called_once_with(1)
    get_tempfile_logger.assert_called_once()
    tee.assert_called_once()

    os.remove("tempfile.log")


@mock.patch("cumulusci.cli.cci.tee_stdout_stderr")
@mock.patch("cumulusci.cli.cci.get_tempfile_logger")
@mock.patch("cumulusci.cli.cci.CliRuntime")
def test_main__CliRuntime_error(CliRuntime, get_tempfile_logger, tee):
    CliRuntime.side_effect = CumulusCIException("something happened")
    get_tempfile_logger.return_value = mock.Mock(), "tempfile.log"

    with contextlib.redirect_stderr(io.StringIO()) as stderr:
        with mock.patch("sys.exit") as sys_exit:
            sys_exit.side_effect = SystemExit  # emulate real sys.exit
            with pytest.raises(SystemExit):
                cci.main(["cci", "org", "info"])

    assert "something happened" in stderr.getvalue()

    tempfile = Path("tempfile.log")
    tempfile.unlink()


@mock.patch("cumulusci.cli.cci.init_logger")  # side effects break other tests
@mock.patch("cumulusci.cli.cci.get_tempfile_logger")
@mock.patch("cumulusci.cli.cci.tee_stdout_stderr")
@mock.patch("cumulusci.cli.cci.CliRuntime")
@mock.patch("sys.exit", MagicMock())
def test_handle_org_name(
    CliRuntime, tee_stdout_stderr, get_tempfile_logger, init_logger
):

    # get_tempfile_logger doesn't clean up after itself which breaks other tests
    get_tempfile_logger.return_value = mock.Mock(), ""

    with contextlib.redirect_stdout(io.StringIO()) as stdout:
        cci.main(["cci", "org", "default", "xyzzy"])
    assert "xyzzy is now the default org" in stdout.getvalue()

    with contextlib.redirect_stdout(io.StringIO()) as stdout:
        cci.main(["cci", "org", "default", "--org", "xyzzy2"])
    assert "xyzzy2 is now the default org" in stdout.getvalue()

    with contextlib.redirect_stderr(io.StringIO()) as stderr:
        cci.main(["cci", "org", "default", "xyzzy1", "--org", "xyzzy2"])
    assert "not both" in stderr.getvalue()

    CliRuntime().keychain.get_default_org.return_value = ("xyzzy3", None)

    # cci org remove should really need an attached org
    with contextlib.redirect_stderr(io.StringIO()) as stderr:
        cci.main(["cci", "org", "remove"])
    assert "Please specify ORGNAME or --org ORGNAME" in stderr.getvalue()


@mock.patch("cumulusci.cli.cci.init_logger")  # side effects break other tests
@mock.patch("cumulusci.cli.cci.get_tempfile_logger")
@mock.patch("cumulusci.cli.cci.tee_stdout_stderr")
@mock.patch("sys.exit")
@mock.patch("cumulusci.cli.cci.CliRuntime")
def test_cci_org_default__no_orgname(
    CliRuntime, exit, tee_stdout_stderr, get_tempfile_logger, init_logger
):
    # get_tempfile_logger doesn't clean up after itself which breaks other tests
    get_tempfile_logger.return_value = mock.Mock(), ""

    CliRuntime().keychain.get_default_org.return_value = ("xyzzy4", None)
    with contextlib.redirect_stdout(io.StringIO()) as stdout:
        cci.main(["cci", "org", "default"])
    assert "xyzzy4 is the default org" in stdout.getvalue()

    CliRuntime().keychain.get_default_org.return_value = (None, None)
    with contextlib.redirect_stdout(io.StringIO()) as stdout:
        cci.main(["cci", "org", "default"])
    assert "There is no default org" in stdout.getvalue()


DEPLOY_CLASS_PATH = f"cumulusci.tasks.salesforce.Deploy{'.Deploy' if sys.version_info >= (3, 11) else ''}"


@mock.patch("cumulusci.cli.cci.init_logger", mock.Mock())
@mock.patch("cumulusci.cli.cci.tee_stdout_stderr", mock.MagicMock())
@mock.patch(f"{DEPLOY_CLASS_PATH}.__call__", mock.Mock())
@mock.patch("sys.exit", mock.Mock())
@mock.patch("cumulusci.cli.cci.get_tempfile_logger")
@mock.patch("cumulusci.cli.cci.CliRuntime")
@mock.patch(f"{DEPLOY_CLASS_PATH}.__init__")
def test_cci_run_task_options__with_dash(
    Deploy,
    CliRuntime,
    get_tempfile_logger,
):
    # get_tempfile_logger doesn't clean up after itself which breaks other tests
    Deploy.return_value = None
    get_tempfile_logger.return_value = mock.Mock(), ""
    CliRuntime.return_value = runtime = mock.Mock()
    runtime.get_org.return_value = ("test", mock.Mock())
    runtime.project_config = BaseProjectConfig(
        runtime.universal_config,
        {
            "project": {"name": "Test"},
            "tasks": {"deploy": {"class_path": "cumulusci.tasks.salesforce.Deploy"}},
        },
    )

    cci.main(
        ["cci", "task", "run", "deploy", "--path", "x", "--clean-meta-xml", "False"]
    )
    task_config = Deploy.mock_calls[0][1][1]
    assert "clean_meta_xml" in task_config.options


@mock.patch("cumulusci.cli.cci.init_logger", mock.Mock())
@mock.patch("cumulusci.cli.cci.tee_stdout_stderr", mock.MagicMock())
@mock.patch(f"{DEPLOY_CLASS_PATH}.__call__", mock.Mock())
@mock.patch("sys.exit", mock.Mock())
@mock.patch("cumulusci.cli.cci.get_tempfile_logger")
@mock.patch("cumulusci.cli.cci.CliRuntime")
@mock.patch(f"{DEPLOY_CLASS_PATH}.__init__")
def test_cci_run_task_options__old_style_with_dash(
    Deploy,
    CliRuntime,
    get_tempfile_logger,
):
    # get_tempfile_logger doesn't clean up after itself which breaks other tests
    Deploy.return_value = None
    get_tempfile_logger.return_value = mock.Mock(), ""
    CliRuntime.return_value = runtime = mock.Mock()
    runtime.get_org.return_value = ("test", mock.Mock())
    runtime.project_config = BaseProjectConfig(
        runtime.universal_config,
        {
            "project": {"name": "Test"},
            "tasks": {"deploy": {"class_path": "cumulusci.tasks.salesforce.Deploy"}},
        },
    )

    cci.main(
        [
            "cci",
            "task",
            "run",
            "deploy",
            "--path",
            "x",
            "-o",
            "clean-meta-xml",
            "False",
        ]
    )
    task_config = Deploy.mock_calls[0][1][1]
    assert "clean_meta_xml" in task_config.options


@mock.patch("cumulusci.cli.cci.open")
@mock.patch("cumulusci.cli.cci.traceback")
def test_handle_exception(traceback, cci_open):
    console = mock.Mock()
    Console.return_value = console
    error_message = "foo"
    cci_open.__enter__.return_value = mock.Mock()

    with contextlib.redirect_stderr(io.StringIO()) as stderr:
        cci.handle_exception(error_message, False, "logfile.path")

    stderr = stderr.getvalue()
    assert f"Error: {error_message}" in stderr
    assert cci.SUGGEST_ERROR_COMMAND in stderr
    traceback.print_exc.assert_called_once()


@mock.patch("cumulusci.cli.cci.open")
def test_handle_exception__error_cmd(cci_open):
    """Ensure we don't write to logfiles when running `cci error ...` commands."""
    error_message = "foo"
    logfile_path = None

    with contextlib.redirect_stderr(io.StringIO()) as stderr:
        cci.handle_exception(error_message, False, logfile_path)

    stderr = stderr.getvalue()
    assert f"Error: {error_message}" in stderr
    assert cci.SUGGEST_ERROR_COMMAND in stderr
    cci_open.assert_not_called()


@mock.patch("cumulusci.cli.cci.open")
@mock.patch("cumulusci.cli.cci.traceback")
def test_handle_click_exception(traceback, cci_open):
    cci_open.__enter__.return_value = mock.Mock()

    with contextlib.redirect_stderr(io.StringIO()) as stderr:
        cci.handle_exception(click.ClickException("[oops]"), False, "file.path")

    stderr = stderr.getvalue()
    assert "Error: [oops]" in stderr
    traceback.assert_not_called()


@mock.patch("cumulusci.cli.cci.open")
def test_handle_connection_exception(cci_open):
    cci_open.__enter__.return_value = mock.Mock()

    with contextlib.redirect_stderr(io.StringIO()) as stderr:
        cci.handle_exception(ConnectionError(), False, "file.log")

    stderr = stderr.getvalue()
    assert "We encountered an error with your internet connection." in stderr


def test_cli():
    run_click_command(cci.cli)


@mock.patch(
    "cumulusci.cli.cci.get_latest_final_version",
    mock.Mock(return_value=version.parse("100")),
)
def test_version(capsys):
    run_click_command(cci.version)
    console_output = capsys.readouterr().out
    assert f"CumulusCI version: {cumulusci.__version__}" in console_output
    assert "There is a newer version of CumulusCI available" in console_output


@mock.patch(
    "cumulusci.cli.cci.get_latest_final_version",
    mock.Mock(return_value=version.parse("1")),
)
def test_version__latest(capsys):
    run_click_command(cci.version)
    console_output = capsys.readouterr().out
    assert "You have the latest version of CumulusCI" in console_output


@mock.patch("cumulusci.cli.cci.warn_if_no_long_paths")
@mock.patch("cumulusci.cli.cci.get_latest_final_version", get_installed_version)
def test_version__win_path_warning(warn_if):
    run_click_command(cci.version)
    warn_if.assert_called_once()


@mock.patch("code.interact")
def test_shell(interact):
    run_click_command(cci.shell)
    interact.assert_called_once()
    assert "config" in interact.call_args[1]["local"]
    assert "runtime" in interact.call_args[1]["local"]


@mock.patch("runpy.run_path")
def test_shell_script(runpy):
    run_click_command(cci.shell, script="foo.py")
    runpy.assert_called_once()
    assert "config" in runpy.call_args[1]["init_globals"]
    assert "runtime" in runpy.call_args[1]["init_globals"]
    assert runpy.call_args[0][0] == "foo.py", runpy.call_args[0]


@mock.patch("builtins.print")
def test_shell_code(print):
    run_click_command(cci.shell, python="print(config, runtime)")
    print.assert_called_once()


@mock.patch("cumulusci.cli.cci.print")
def test_shell_mutually_exclusive_args(print):
    with pytest.raises(Exception) as e:
        run_click_command(cci.shell, script="foo.py", python="print(config, runtime)")
    assert "Cannot specify both" in e.value.message


@mock.patch("code.interact")
def test_shell__no_project(interact):
    with temporary_dir():
        run_click_command(cci.shell)
        interact.assert_called_once()


def test_cover_command_groups():
    run_click_command(cci.project)
    run_click_command(cci.org)
    run_click_command(cci.task)
    run_click_command(cci.flow)
    run_click_command(cci.service)
    # no assertion; this test is for coverage of empty methods


@mock.patch(
    "cumulusci.cli.runtime.CliRuntime.get_org",
    lambda *args, **kwargs: (MagicMock(), MagicMock()),
)
@mock.patch("cumulusci.core.runtime.BaseCumulusCI._load_keychain", MagicMock())
@mock.patch("pdb.post_mortem", MagicMock())
@mock.patch("cumulusci.cli.cci.tee_stdout_stderr", MagicMock())
@mock.patch("cumulusci.cli.cci.init_logger", MagicMock())
@mock.patch("cumulusci.cli.cci.get_tempfile_logger")
def test_run_task_debug(get_tempfile_logger):
    get_tempfile_logger.return_value = (mock.Mock(), "tempfile.log")

    gipnew = "cumulusci.tasks.preflight.packages.GetInstalledPackages._run_task"
    with mock.patch(gipnew, mock_validate_debug(False)):
        cci.main(["cci", "task", "run", "get_installed_packages"])
    with mock.patch(gipnew, mock_validate_debug(True)):
        cci.main(["cci", "task", "run", "get_installed_packages", "--debug"])


@mock.patch(
    "cumulusci.cli.runtime.CliRuntime.get_org",
    lambda *args, **kwargs: (MagicMock(), MagicMock()),
)
@mock.patch("cumulusci.core.runtime.BaseCumulusCI._load_keychain", MagicMock())
@mock.patch("pdb.post_mortem", MagicMock())
@mock.patch("cumulusci.cli.cci.tee_stdout_stderr", MagicMock())
@mock.patch("cumulusci.cli.cci.init_logger", MagicMock())
@mock.patch("cumulusci.tasks.robotframework.RobotLibDoc", MagicMock())
@mock.patch("cumulusci.cli.cci.get_tempfile_logger")
def test_run_flow_debug(get_tempfile_logger):
    get_tempfile_logger.return_value = (mock.Mock(), "tempfile.log")
    rtd = "cumulusci.tasks.robotframework.RobotTestDoc._run_task"

    with mock.patch(rtd, mock_validate_debug(False)):
        cci.main(["cci", "flow", "run", "robot_docs"])
    with mock.patch(rtd, mock_validate_debug(True)):
        cci.main(["cci", "flow", "run", "robot_docs", "--debug"])


def mock_validate_debug(value):
    def _run_task(self, *args, **kwargs):
        assert bool(self.debug_mode) == bool(value)

    return _run_task


@mock.patch("cumulusci.cli.cci.tee_stdout_stderr")
@mock.patch("cumulusci.cli.cci.get_tempfile_logger")
@mock.patch("cumulusci.cli.cci.init_logger")
@mock.patch("cumulusci.cli.cci.check_latest_version")
@mock.patch("cumulusci.cli.cci.CliRuntime")
@mock.patch("cumulusci.cli.cci.show_version_info")
def test_dash_dash_version(
    show_version_info,
    CliRuntime,
    check_latest_version,
    init_logger,
    get_tempfile_logger,
    tee,
):
    get_tempfile_logger.return_value = mock.Mock(), "tempfile.log"
    cci.main(["cci", "--help"])
    assert len(show_version_info.mock_calls) == 0

    cci.main(["cci", "version"])
    assert len(show_version_info.mock_calls) == 1

    cci.main(["cci", "--version"])
    assert len(show_version_info.mock_calls) == 2


# Sentry helper function tests


class TestSentryEnvironment:
    """Tests for _get_sentry_environment()"""

    def test_returns_development_for_dev_version(self):
        with mock.patch.object(cumulusci, "__version__", "4.0.0.dev1"):
            assert cci._get_sentry_environment() == "development"

    def test_returns_development_for_alpha_version(self):
        with mock.patch.object(cumulusci, "__version__", "4.0.0alpha1"):
            assert cci._get_sentry_environment() == "development"

    def test_returns_development_for_beta_version(self):
        with mock.patch.object(cumulusci, "__version__", "4.0.0beta1"):
            assert cci._get_sentry_environment() == "development"

    def test_returns_development_for_rc_version(self):
        with mock.patch.object(cumulusci, "__version__", "4.0.0rc1"):
            assert cci._get_sentry_environment() == "development"

    def test_returns_development_for_unknown_version(self):
        with mock.patch.object(cumulusci, "__version__", "unknown"):
            assert cci._get_sentry_environment() == "development"

    def test_returns_production_for_release_version(self):
        with mock.patch.object(cumulusci, "__version__", "4.0.0"):
            assert cci._get_sentry_environment() == "production"

    def test_env_var_override(self):
        with mock.patch.dict(os.environ, {"CCI_ENVIRONMENT": "staging"}):
            assert cci._get_sentry_environment() == "staging"


class TestAnonymousUserId:
    """Tests for _get_anonymous_user_id()"""

    def test_returns_consistent_id(self):
        """User ID should be consistent across calls"""
        id1 = cci._get_anonymous_user_id()
        id2 = cci._get_anonymous_user_id()
        assert id1 == id2

    def test_returns_16_char_hex_string(self):
        """User ID should be a 16-character hex string"""
        user_id = cci._get_anonymous_user_id()
        assert len(user_id) == 16
        assert all(c in "0123456789abcdef" for c in user_id)

    def test_different_machines_different_ids(self):
        """Different machine identifiers should produce different IDs"""
        with mock.patch("platform.node", return_value="machine1"):
            id1 = cci._get_anonymous_user_id()
        with mock.patch("platform.node", return_value="machine2"):
            id2 = cci._get_anonymous_user_id()
        assert id1 != id2


class TestDetectCiEnvironment:
    """Tests for _detect_ci_environment()"""

    def test_detects_github_actions(self):
        with mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}, clear=True):
            assert cci._detect_ci_environment() == "github_actions"

    def test_detects_circleci(self):
        with mock.patch.dict(os.environ, {"CIRCLECI": "true"}, clear=True):
            assert cci._detect_ci_environment() == "circleci"

    def test_detects_gitlab(self):
        with mock.patch.dict(os.environ, {"GITLAB_CI": "true"}, clear=True):
            assert cci._detect_ci_environment() == "gitlab"

    def test_detects_jenkins(self):
        with mock.patch.dict(os.environ, {"JENKINS_URL": "http://jenkins"}, clear=True):
            assert cci._detect_ci_environment() == "jenkins"

    def test_detects_bitbucket(self):
        with mock.patch.dict(os.environ, {"BITBUCKET_PIPELINES": "true"}, clear=True):
            assert cci._detect_ci_environment() == "bitbucket"

    def test_detects_jenkins_via_jenkins_home(self):
        with mock.patch.dict(os.environ, {"JENKINS_HOME": "/var/jenkins"}, clear=True):
            assert cci._detect_ci_environment() == "jenkins"

    def test_detects_azure_devops_via_tf_build(self):
        with mock.patch.dict(os.environ, {"TF_BUILD": "true"}, clear=True):
            assert cci._detect_ci_environment() == "azure_devops"

    def test_detects_unknown_ci(self):
        with mock.patch.dict(os.environ, {"CI": "true"}, clear=True):
            assert cci._detect_ci_environment() == "unknown_ci"

    def test_returns_none_when_not_in_ci(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            assert cci._detect_ci_environment() is None


class TestInitSentry:
    """Tests for init_sentry()"""

    @mock.patch("sentry_sdk.init")
    def test_does_not_init_when_telemetry_disabled(self, sentry_init):
        with mock.patch.dict(os.environ, {}, clear=True):
            cci.init_sentry()
        sentry_init.assert_not_called()

    @mock.patch("sentry_sdk.init")
    @mock.patch("cumulusci.cli.cci._set_sentry_user_context")
    def test_inits_when_telemetry_enabled_with_1(self, set_context, sentry_init):
        with mock.patch.dict(os.environ, {"CCI_ENABLE_TELEMETRY": "1"}, clear=True):
            cci.init_sentry()
        sentry_init.assert_called_once()
        set_context.assert_called_once()

    @mock.patch("sentry_sdk.init")
    @mock.patch("cumulusci.cli.cci._set_sentry_user_context")
    def test_inits_when_telemetry_enabled_with_true(self, set_context, sentry_init):
        with mock.patch.dict(os.environ, {"CCI_ENABLE_TELEMETRY": "true"}, clear=True):
            cci.init_sentry()
        sentry_init.assert_called_once()

    @mock.patch("sentry_sdk.init")
    @mock.patch("cumulusci.cli.cci._set_sentry_user_context")
    def test_inits_when_telemetry_enabled_with_yes(self, set_context, sentry_init):
        with mock.patch.dict(os.environ, {"CCI_ENABLE_TELEMETRY": "yes"}, clear=True):
            cci.init_sentry()
        sentry_init.assert_called_once()

    @mock.patch("sentry_sdk.init")
    @mock.patch("cumulusci.cli.cci._set_sentry_user_context")
    def test_uses_custom_dsn_from_env(self, set_context, sentry_init):
        custom_dsn = "https://custom@sentry.io/123"
        with mock.patch.dict(
            os.environ,
            {"CCI_ENABLE_TELEMETRY": "1", "SENTRY_DSN": custom_dsn},
            clear=True,
        ):
            cci.init_sentry()
        assert sentry_init.call_args[1]["dsn"] == custom_dsn

    @mock.patch("sentry_sdk.init")
    @mock.patch("cumulusci.cli.cci._set_sentry_user_context")
    def test_sets_release_to_version(self, set_context, sentry_init):
        with mock.patch.dict(os.environ, {"CCI_ENABLE_TELEMETRY": "1"}, clear=True):
            cci.init_sentry()
        assert sentry_init.call_args[1]["release"] == cumulusci.__version__

    @mock.patch("sentry_sdk.init")
    @mock.patch("cumulusci.cli.cci._set_sentry_user_context")
    def test_disables_pii(self, set_context, sentry_init):
        with mock.patch.dict(os.environ, {"CCI_ENABLE_TELEMETRY": "1"}, clear=True):
            cci.init_sentry()
        assert sentry_init.call_args[1]["send_default_pii"] is False

    @mock.patch("sentry_sdk.init")
    def test_handles_invalid_dsn_gracefully(self, sentry_init, capsys):
        """Invalid DSN should not crash the CLI"""
        sentry_init.side_effect = Exception("Invalid DSN")
        with mock.patch.dict(os.environ, {"CCI_ENABLE_TELEMETRY": "1"}, clear=True):
            cci.init_sentry()  # Should not raise
        stderr = capsys.readouterr().err
        assert "Warning" in stderr
        assert "Telemetry disabled" in stderr


class TestSetSentryUserContext:
    """Tests for _set_sentry_user_context()"""

    @mock.patch("sentry_sdk.set_tag")
    @mock.patch("sentry_sdk.set_context")
    @mock.patch("sentry_sdk.set_user")
    def test_sets_anonymous_user_id(self, set_user, set_context, set_tag):
        cci._set_sentry_user_context()
        set_user.assert_called_once()
        user_data = set_user.call_args[0][0]
        assert "id" in user_data
        assert len(user_data["id"]) == 16

    @mock.patch("sentry_sdk.set_tag")
    @mock.patch("sentry_sdk.set_context")
    @mock.patch("sentry_sdk.set_user")
    def test_sets_os_context(self, set_user, set_context, set_tag):
        cci._set_sentry_user_context()
        os_call = [c for c in set_context.call_args_list if c[0][0] == "os"]
        assert len(os_call) == 1
        os_data = os_call[0][0][1]
        assert "name" in os_data
        assert "version" in os_data
        assert "build" in os_data

    @mock.patch("sentry_sdk.set_tag")
    @mock.patch("sentry_sdk.set_context")
    @mock.patch("sentry_sdk.set_user")
    def test_sets_device_context(self, set_user, set_context, set_tag):
        cci._set_sentry_user_context()
        device_call = [c for c in set_context.call_args_list if c[0][0] == "device"]
        assert len(device_call) == 1
        device_data = device_call[0][0][1]
        assert "arch" in device_data

    @mock.patch("sentry_sdk.set_tag")
    @mock.patch("sentry_sdk.set_context")
    @mock.patch("sentry_sdk.set_user")
    def test_sets_ci_tag_when_in_ci(self, set_user, set_context, set_tag):
        with mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}):
            cci._set_sentry_user_context()
        set_tag.assert_called_once_with("ci", "github_actions")

    @mock.patch("sentry_sdk.set_tag")
    @mock.patch("sentry_sdk.set_context")
    @mock.patch("sentry_sdk.set_user")
    def test_does_not_set_ci_tag_when_not_in_ci(self, set_user, set_context, set_tag):
        with mock.patch.dict(os.environ, {}, clear=True):
            cci._set_sentry_user_context()
        set_tag.assert_not_called()


class TestTelemetryCommand:
    """Tests for cci telemetry command"""

    def test_shows_disabled_by_default(self, capsys):
        with mock.patch.dict(os.environ, {}, clear=True):
            run_click_command(cci.telemetry)
        output = capsys.readouterr().out
        assert "DISABLED" in output
        assert "CCI_ENABLE_TELEMETRY" in output

    def test_shows_enabled_when_set(self, capsys):
        with mock.patch.dict(os.environ, {"CCI_ENABLE_TELEMETRY": "1"}, clear=True):
            run_click_command(cci.telemetry)
        output = capsys.readouterr().out
        assert "ENABLED" in output

    def test_shows_version(self, capsys):
        run_click_command(cci.telemetry)
        output = capsys.readouterr().out
        assert cumulusci.__version__ in output

    def test_shows_anonymous_user_id(self, capsys):
        run_click_command(cci.telemetry)
        output = capsys.readouterr().out
        assert "Anonymous User ID" in output

    def test_shows_os_context(self, capsys):
        run_click_command(cci.telemetry)
        output = capsys.readouterr().out
        assert "OS Context" in output
        assert "Name:" in output
        assert "Version:" in output

    def test_shows_not_collected_data(self, capsys):
        run_click_command(cci.telemetry)
        output = capsys.readouterr().out
        assert "NOT collected" in output
        assert "Salesforce credentials" in output

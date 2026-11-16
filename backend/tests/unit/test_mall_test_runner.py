"""TDD for the isolated test runner: no real Docker or network in these tests."""

import importlib.util
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def runner():
    spec = importlib.util.spec_from_file_location(
        "mall_test_runner", ROOT / "scripts/mall_test_runner.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_inherited_database_target_is_refused_before_any_process(runner):
    calls = []
    with pytest.raises(ValueError, match="database target"):
        runner.run_suite(
            "backend-mysql",
            {"MALL_TEST_DATABASE_URL": "mysql://remote/real"},
            calls.append,
        )
    assert calls == []


def test_invalid_suite_is_refused_without_starting_docker(runner):
    calls = []
    with pytest.raises(ValueError, match="suite"):
        runner.run_suite("anything", {}, calls.append)
    assert calls == []


def fake_process(calls, fail_at=None):
    def run(args, **kwargs):
        calls.append((args, kwargs))
        text = " ".join(map(str, args))
        if fail_at and fail_at in text:
            raise subprocess.CalledProcessError(17, args)
        output = ""
        if args[:3] == ["docker", "context", "inspect"]:
            output = "unix:///tmp/mall-test.sock"
        elif "inspect" in args:
            output = args[-1].removeprefix("malltest_")
        elif "port" in args:
            output = "127.0.0.1:13306"
        return subprocess.CompletedProcess(args, 0, stdout=output, stderr="")

    return run


def test_mysql_suite_is_migrated_and_cleaned_up_even_after_test_failure(runner):
    calls = []
    status = runner.run_suite("backend-mysql", {}, fake_process(calls, "-m pytest"))
    assert status == 17
    commands = [" ".join(map(str, args)) for args, _ in calls]
    assert any("mall_bootstrap.py" in command for command in commands)
    assert any("tests/mysql" in command for command in commands)
    pytest_command = next(args for args, _ in calls if "-m" in args and "pytest" in args)
    assert "-s" in pytest_command and "--durations=0" in pytest_command
    assert "down --volumes" in commands[-1]
    assert all("prune" not in command for command in commands)


def test_failed_startup_still_cleans_only_the_unique_compose_project(runner):
    calls = []
    assert runner.run_suite("backend-mysql", {}, fake_process(calls, "up --wait")) == 17
    commands = [args for args, _ in calls]
    start = next(args for args in commands if "up" in args)
    finish = commands[-1]
    assert start[start.index("--project-name") + 1].startswith("malltest_")
    assert finish[finish.index("--project-name") + 1] == start[start.index("--project-name") + 1]
    assert "down" in finish and "--volumes" in finish


def test_runner_uses_clean_environment_and_hides_credentials(runner):
    calls = []
    source = {
        "COS_SECRET_KEY": "do-not-copy",
        "WECHAT_APP_SECRET": "do-not-copy",
        "PATH": "/bin",
    }
    assert runner.run_suite("backend-mysql", source, fake_process(calls)) == 0
    child = next(
        kwargs for args, kwargs in calls if "mall_bootstrap.py" in " ".join(map(str, args))
    )
    env = child["env"]
    assert "COS_SECRET_KEY" not in env and "WECHAT_APP_SECRET" not in env
    assert env["DATABASE_URL"] == "sqlite+aiosqlite:///:memory:"
    assert "do-not-copy" not in repr(calls)
    assert child["cwd"] != str(ROOT / "backend")
    assert "MALL_TEST_RUN_ID" in env and "MALL_TEST_CA_FILE" in env


def test_dependency_check_does_not_start_database(runner):
    calls = []
    assert runner.run_suite("check", {}, fake_process(calls)) == 0
    assert not any("up" in args for args, _ in calls)


def test_public_image_access_uses_only_temporary_docker_credentials(runner):
    import json

    calls = []
    normal = fake_process(calls)

    def execute(args, **kwargs):
        if "up" in args:
            env = kwargs["env"]
            assert env["DOCKER_HOST"] == "unix:///tmp/mall-test.sock"
            assert "DOCKER_CONTEXT" not in env
            config = Path(env["DOCKER_CONFIG"]) / "config.json"
            assert config.parent.parent == Path(kwargs["cwd"])
            assert json.loads(config.read_text())["auths"] == {}
            assert "credsStore" not in json.loads(config.read_text())
        return normal(args, **kwargs)

    assert runner.run_suite("backend-mysql", {"HOME": "/some/home"}, execute) == 0


def test_remote_docker_endpoint_is_not_authorized_by_local_test_run(runner):
    calls = []
    normal = fake_process(calls)

    def execute(args, **kwargs):
        if args[:3] == ["docker", "context", "inspect"]:
            return subprocess.CompletedProcess(args, 0, stdout="tcp://remote.invalid:2375")
        return normal(args, **kwargs)

    with pytest.raises(ValueError, match="local Docker"):
        runner.run_suite("backend-mysql", {}, execute)
    assert not any("up" in args for args, _ in calls)


def test_startup_diagnostic_is_useful_but_does_not_reveal_generated_password(runner, capsys):
    calls = []
    normal = fake_process(calls)
    passwords = []

    def execute(args, **kwargs):
        if "up" in args:
            env_file = Path(args[args.index("--env-file") + 1])
            values = dict(line.split("=", 1) for line in env_file.read_text().splitlines())
            passwords.append(values["MYSQL_PASSWORD"])
            raise subprocess.CalledProcessError(
                17, args, stderr=("controlled public failure: " + passwords[-1]).encode()
            )
        return normal(args, **kwargs)

    assert runner.run_suite("backend-mysql", {}, execute) == 17
    output = capsys.readouterr().err
    assert "controlled public failure" in output
    assert passwords[0] not in output


def test_standalone_compose_is_supported_without_changing_docker_configuration(runner):
    calls = []
    normal = fake_process(calls)

    def execute(args, **kwargs):
        if args[:3] == ["docker", "compose", "version"]:
            raise subprocess.CalledProcessError(1, args)
        return normal(args, **kwargs)

    assert runner.run_suite("backend-mysql", {}, execute) == 0
    assert any(args[:2] == ["docker-compose", "version"] for args, _ in calls)
    assert any(args[0] == "docker-compose" and "up" in args for args, _ in calls)


def test_cleanup_error_does_not_hide_the_original_failure(runner):
    calls = []
    normal = fake_process(calls, "-m pytest")

    def execute(args, **kwargs):
        if "down" in args:
            raise subprocess.TimeoutExpired(args, 45)
        return normal(args, **kwargs)

    assert runner.run_suite("backend-mysql", {}, execute) == 17


def test_foreign_container_identity_is_rejected_and_no_database_process_runs(runner):
    calls = []
    normal = fake_process(calls)

    def execute(args, **kwargs):
        if "inspect" in args and "context" not in args:
            return subprocess.CompletedProcess(args, 0, stdout="not-this-run", stderr="")
        return normal(args, **kwargs)

    with pytest.raises(ValueError, match="ownership"):
        runner.run_suite("backend-mysql", {}, execute)
    assert not any("mall_bootstrap.py" in " ".join(map(str, args)) for args, _ in calls)

"""One-command, disposable test environment. Never accepts a database URL."""

import argparse
import json
import os
import secrets
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "backend/docker-compose.mall-test.yml"


def run_suite(suite, source_env=None, execute=subprocess.run):
    source_env = os.environ if source_env is None else source_env
    if suite not in {"all", "backend-mysql", "check"}:
        raise ValueError("invalid suite")
    if source_env.get("MALL_TEST_DATABASE_URL") or source_env.get("MALL_TEST_RUN_ID"):
        raise ValueError("externally supplied database target is forbidden")
    if sys.version_info < (3, 11):
        raise RuntimeError("Python 3.11+ is required")
    # In particular, do not inherit application, channel, COS, DB or cloud credentials.
    env = {
        key: source_env[key]
        for key in ("PATH", "HOME", "TMPDIR", "DOCKER_HOST", "DOCKER_CONTEXT")
        if key in source_env
    }
    python = ROOT / "backend/.venv/bin/python"
    if not python.exists():
        execute([sys.executable, "-m", "venv", str(python.parents[1])], check=True, env=env)
        execute(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "-r",
                str(ROOT / "backend/requirements.txt"),
            ],
            check=True,
            env=env,
        )
    dependency_probe = [str(python), "-c", "import pytest, sqlalchemy, aiomysql, alembic"]
    try:
        execute(dependency_probe, check=True, env=env)
    except subprocess.CalledProcessError:
        execute(
            [str(python), "-m", "pip", "install", "-r", str(ROOT / "backend/requirements.txt")],
            check=True,
            env=env,
        )
        execute(dependency_probe, check=True, env=env)
    compose_cli = ["docker", "compose"]
    try:
        execute(compose_cli + ["version"], check=True, env=env, capture_output=True)
    except subprocess.CalledProcessError:
        compose_cli = ["docker-compose"]
        execute(compose_cli + ["version"], check=True, env=env, capture_output=True)
    endpoint = env.get("DOCKER_HOST") or execute(
        ["docker", "context", "inspect", "--format", "{{ .Endpoints.docker.Host }}"],
        check=True, capture_output=True, text=True, env=env,
    ).stdout.strip()
    if not endpoint.startswith("unix:///") or any(x in endpoint for x in ("\x00", "\n", "\r")):
        raise ValueError("Only a local Docker socket is allowed")
    env["DOCKER_HOST"] = endpoint
    env.pop("DOCKER_CONTEXT", None)
    execute(
        ["docker", "info", "--format", "{{.ServerVersion}}"],
        check=True,
        env=env,
        capture_output=True,
        timeout=15,
    )
    if suite == "check":
        return 0
    run_id = secrets.token_hex(16)
    password = secrets.token_hex(24)
    root_password = secrets.token_hex(24)
    owner = secrets.token_hex(32)
    with tempfile.TemporaryDirectory(prefix="bjrutai_mall_test_") as directory:
        work = Path(directory)
        # Public test images do not need the user's registry credentials or a
        # credential helper that may belong to another Docker installation.
        docker_config = work / "docker-client"
        docker_config.mkdir(mode=0o700)
        (docker_config / "config.json").write_text(json.dumps({
            "auths": {},
            "cliPluginsExtraDirs": [
                str(Path(env.get("HOME", "/nonexistent")) / ".docker/cli-plugins"),
                "/opt/homebrew/lib/docker/cli-plugins",
                "/usr/local/lib/docker/cli-plugins",
            ],
        }))
        env["DOCKER_CONFIG"] = str(docker_config)
        credentials = work / "mysql.env"
        credentials.write_text(
            f"MALL_TEST_RUN_ID={run_id}\nMYSQL_ROOT_PASSWORD={root_password}\n"
            f"MYSQL_DATABASE=bjrutai_mall_test_{run_id}\nMYSQL_USER=mall_runner\n"
            f"MYSQL_PASSWORD={password}\n"
        )
        credentials.chmod(0o600)
        compose = compose_cli + [
            "--file",
            str(COMPOSE),
            "--project-name",
            f"malltest_{run_id}",
            "--env-file",
            str(credentials),
        ]
        env.update(
            DATABASE_URL="sqlite+aiosqlite:///:memory:",
            RUTAI_MOCK="true",
            RATE_LIMIT_ENABLED="false",
            PYTHONPATH=str(ROOT / "backend"),
            MALL_TEST_RUN_ID=run_id,
            MALL_TEST_OWNER_TOKEN=owner,
            MALL_TEST_CA_FILE=str(work / "ca.pem"),
            MALL_GATEWAY_MODE="test",
            MALL_ENABLED="false",
            MALL_PURCHASE_ENABLED="false",
            MALL_GATEWAY_OUTBOUND_ENABLED="false",
            MALL_STORAGE_OUTBOUND_ENABLED="false",
            MALL_WORKER_ENABLED="false",
            SCHEMA_AUTO_CREATE_ENABLED="false",
            APP_ENVIRONMENT="test",
        )
        status = 0
        try:
            execute(
                compose + ["up", "--wait", "--wait-timeout", "120"],
                check=True,
                cwd=str(work),
                env=env,
                capture_output=True,
                timeout=150,
            )
            identity = execute(
                [
                    "docker",
                    "inspect",
                    "--format",
                    '{{ index .Config.Labels "com.bjrutai.mall-test-run" }}',
                    f"malltest_{run_id}",
                ],
                check=True,
                capture_output=True,
                text=True,
                env=env,
            ).stdout.strip()
            if identity != run_id:
                raise ValueError("test container ownership mismatch")
            port = execute(
                compose + ["port", "mysql", "3306"],
                check=True,
                capture_output=True,
                text=True,
                env=env,
            ).stdout.strip()
            host, separator, number = port.rpartition(":")
            if host != "127.0.0.1" or not separator or not number.isdecimal():
                raise ValueError("invalid test database endpoint")
            env["MALL_TEST_DATABASE_URL"] = (
                f"mysql+aiomysql://mall_runner:{password}@127.0.0.1:{number}/"
                f"bjrutai_mall_test_{run_id}?charset=utf8mb4"
            )
            execute(
                compose + ["cp", "mysql:/var/lib/mysql/ca.pem", env["MALL_TEST_CA_FILE"]],
                check=True,
                env=env,
                capture_output=True,
            )
            execute(
                [str(python), str(ROOT / "backend/tests/mall_bootstrap.py")],
                check=True,
                cwd=str(work),
                env=env,
                capture_output=True,
            )
            test_paths = [str(ROOT / "backend/tests/mysql")]
            if suite == "all":
                test_paths += [
                    str(ROOT / "backend/tests/unit"),
                    str(ROOT / "backend/tests/contract"),
                    str(ROOT / "backend/tests/integration"),
                ]
            execute(
                [
                    str(python),
                    "-m",
                    "pytest",
                    "-c",
                    str(ROOT / "backend/pyproject.toml"),
                    *test_paths,
                    "-q",
                    "--tb=short",
                    "-x",
                ],
                check=True,
                cwd=str(work),
                env=env,
            )
            if suite == "all":
                admin = ROOT / "manageSystem"
                if not (admin / "node_modules").exists():
                    execute(["npm", "ci"], check=True, cwd=str(admin), env=env)
                execute(
                    ["npm", "exec", "--", "vitest", "run"],
                    check=True,
                    cwd=str(admin),
                    env=env,
                )
                mini = ROOT / "miniProgram"
                tests = sorted(str(p) for p in (mini / "tests").rglob("*.test.js"))
                if tests:
                    execute(["node", "--test", *tests], check=True, cwd=str(mini), env=env)
        except subprocess.CalledProcessError as exc:
            # Do not print captured SQL/credentials or the inherited environment.
            status = exc.returncode if exc.returncode > 0 else 1
            print(
                f"Mall test stage failed (exit {status}); cleaning this run only.",
                file=sys.stderr,
            )
            diagnostic = exc.stderr or b""
            if isinstance(diagnostic, bytes):
                diagnostic = diagnostic.decode("utf-8", errors="replace")
            for secret in (password, root_password, owner):
                diagnostic = diagnostic.replace(secret, "[redacted]")
            diagnostic = "".join(c for c in diagnostic if c.isprintable() or c == "\n")
            if diagnostic:
                print(diagnostic[-1800:], file=sys.stderr)
        finally:
            try:
                result = execute(
                    compose + ["down", "--volumes", "--remove-orphans"],
                    check=False,
                    cwd=str(work),
                    env=env,
                    capture_output=True,
                    timeout=45,
                )
                if result.returncode and status == 0:
                    status = result.returncode
            except (OSError, subprocess.SubprocessError):
                print(
                    f"Cleanup incomplete for project malltest_{run_id}; "
                    "only that project may be removed.",
                    file=sys.stderr,
                )
                if status == 0:
                    status = 2
        return status


def main():
    def interrupted(signum, _frame):
        raise SystemExit(128 + signum)  # Unwind the resource-cleanup finally block.

    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--backend-mysql", action="store_true")
    group.add_argument("--check", action="store_true")
    args = parser.parse_args()
    suite = "check" if args.check else "backend-mysql" if args.backend_mysql else "all"
    try:
        return run_suite(suite)
    except (ValueError, RuntimeError, FileNotFoundError, subprocess.SubprocessError):
        print(
            "Mall tests could not start safely. Check Python dependencies and Docker access; "
            "no external database URL is accepted.",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

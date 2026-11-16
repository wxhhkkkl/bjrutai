"""Fail-closed helpers shared by disposable MySQL tests and their bootstrap."""

import os
import re
import ssl
from urllib.parse import urlsplit

import httpx
from sqlalchemy import text


def owned_mysql_url(environment=None):
    env = os.environ if environment is None else environment
    run_id = env.get("MALL_TEST_RUN_ID", "")
    token = env.get("MALL_TEST_OWNER_TOKEN", "")
    url = env.get("MALL_TEST_DATABASE_URL", "")
    try:
        parsed = urlsplit(url)
        valid = (
            re.fullmatch(r"[0-9a-f]{32}", run_id)
            and re.fullmatch(r"[0-9a-f]{64}", token)
            and parsed.scheme == "mysql+aiomysql"
            and parsed.hostname == "127.0.0.1"
            and parsed.username == "mall_runner"
            and bool(parsed.password)
            and parsed.port
            and 1024 < parsed.port <= 65535
            and parsed.port != 3306
            and parsed.path == f"/bjrutai_mall_test_{run_id}"
            and parsed.query in {"", "charset=utf8mb4"}
            and not parsed.fragment
        )
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("A runner-owned isolated MySQL target is required")
    return url


def mysql_test_ssl(environment=None):
    env = os.environ if environment is None else environment
    owned_mysql_url(env)
    # The container's auto-generated certificate is signed by the CA copied
    # from that ownership-verified container, but has no loopback-IP SAN.
    # This exception is test-only: CA verification and TLS remain mandatory.
    context = ssl.create_default_context(cafile=env["MALL_TEST_CA_FILE"])
    context.check_hostname = False
    return context


async def verify_mysql_owner(connection, environment=None):
    env = os.environ if environment is None else environment
    owned_mysql_url(env)
    cipher = (await connection.execute(text("SHOW SESSION STATUS LIKE 'Ssl_cipher'"))).first()
    if not cipher or not cipher[1]:
        raise ValueError("isolated MySQL TLS is required")
    row = (
        await connection.execute(text("SELECT run_id, owner_token FROM mall_test_owner WHERE id=1"))
    ).first()
    if not row or tuple(row) != (env["MALL_TEST_RUN_ID"], env["MALL_TEST_OWNER_TOKEN"]):
        raise ValueError("isolated MySQL ownership mismatch")


def fake_mall_transport(responses):
    def respond(request):
        if not request.url.host or not request.url.host.endswith(".test"):
            raise AssertionError("Only a test host is allowed")
        key = request.method, request.url.path
        if key not in responses:
            raise AssertionError("Unconfigured fake channel request")
        return httpx.Response(200, json=responses[key])

    return httpx.MockTransport(respond)

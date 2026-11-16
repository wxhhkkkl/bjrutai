"""The MySQL fixture must reject an unsafe target before making a connection."""

import importlib

import pytest

RUN = "a" * 32


def environment():
    return {
        "MALL_TEST_RUN_ID": RUN,
        "MALL_TEST_OWNER_TOKEN": "b" * 64,
        "MALL_TEST_DATABASE_URL": (
            f"mysql+aiomysql://mall_runner:test-secret@127.0.0.1:13306/bjrutai_mall_test_{RUN}"
        ),
    }


def fixture_tools():
    return importlib.import_module("tests.mall_fixtures")


@pytest.mark.parametrize(
    "change",
    [
        {"MALL_TEST_RUN_ID": ""},
        {"MALL_TEST_OWNER_TOKEN": ""},
        {"MALL_TEST_DATABASE_URL": "mysql+aiomysql://mall_runner:x@production.invalid/bjrutai"},
        {
            "MALL_TEST_DATABASE_URL": f"mysql+aiomysql://root:x@127.0.0.1:13306/bjrutai_mall_test_{RUN}"
        },
        {
            "MALL_TEST_DATABASE_URL": f"mysql+aiomysql://mall_runner:x@127.0.0.1:3306/bjrutai_mall_test_{RUN}"
        },
        {
            "MALL_TEST_DATABASE_URL": (
                "mysql+aiomysql://mall_runner:x@127.0.0.1:13306/bjrutai_mall_test_" + "c" * 32
            )
        },
    ],
)
def test_unsafe_database_configuration_fails_closed(change):
    env = environment()
    env.update(change)
    with pytest.raises(ValueError, match="isolated MySQL"):
        fixture_tools().owned_mysql_url(env)


def test_owned_loopback_url_is_accepted_without_opening_it():
    env = environment()
    assert fixture_tools().owned_mysql_url(env) == env["MALL_TEST_DATABASE_URL"]


def test_fake_transport_has_no_unconfigured_network_fallback():
    import httpx

    transport = fixture_tools().fake_mall_transport({("POST", "/pay"): {"status": "pending"}})
    with httpx.Client(transport=transport) as client:
        assert client.post("https://channel.test/pay").json() == {"status": "pending"}
        with pytest.raises(AssertionError, match="Unconfigured fake"):
            client.post("https://channel.test/refund")
        with pytest.raises(AssertionError, match="test host"):
            client.post("https://pay.wechatpay.cn/pay")

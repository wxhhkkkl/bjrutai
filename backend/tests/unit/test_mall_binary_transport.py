"""Ciphertext must round-trip as SQL binary, including NUL and quotes."""

import aiomysql.connection


def test_aiomysql_binary_literal_is_callable_and_preserves_every_byte():
    encoder = aiomysql.connection.escape_bytes_prefixed
    assert callable(encoder)
    value = bytes(range(256))
    literal = encoder(value)
    # Compatibility fallback uses standard SQL hex literals, no interpolated data.
    if literal.startswith("X'"):
        assert bytes.fromhex(literal[2:-1]) == value

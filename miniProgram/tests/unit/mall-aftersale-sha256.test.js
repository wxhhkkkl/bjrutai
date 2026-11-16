const test = require('node:test')
const assert = require('node:assert/strict')

const { sha256Hex } = require('../../utils/sha256')

test('computes standard SHA-256 vectors for empty input and abc', () => {
  assert.equal(
    sha256Hex(new ArrayBuffer(0)),
    'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'
  )
  assert.equal(
    sha256Hex(Uint8Array.from([97, 98, 99])),
    'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'
  )
})

test('hashes only the visible byte range of a typed array', () => {
  const parent = Uint8Array.from([0, 97, 98, 99, 0])
  assert.equal(
    sha256Hex(parent.subarray(1, 4)),
    'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'
  )
})

test('handles the SHA-256 multi-block padding boundary vector', () => {
  const input = 'abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq'
  const bytes = Uint8Array.from(input, (character) => character.charCodeAt(0))
  assert.equal(
    sha256Hex(bytes),
    '248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1'
  )
})

test('rejects values that are not binary data', () => {
  assert.throws(() => sha256Hex('abc'), /二进制/)
})

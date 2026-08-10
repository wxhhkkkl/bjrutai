const test = require('node:test')
const assert = require('node:assert/strict')

const { createRequestKeyManager } = require('../../utils/request-key')

test('reuses a key while a result is submitting or unknown', () => {
  let sequence = 0
  const manager = createRequestKeyManager(() => `key-${++sequence}`)

  const first = manager.begin('binding:customer-1')
  manager.markUnknown('binding:customer-1')
  const retry = manager.begin('binding:customer-1')

  assert.equal(first, retry)
  assert.equal(sequence, 1)
})

test('creates a new key after explicit failure reset or a new flow', () => {
  let sequence = 0
  const manager = createRequestKeyManager(() => `key-${++sequence}`)
  const first = manager.begin('feedback:new')
  manager.markFailed('feedback:new')
  const second = manager.begin('feedback:new')
  manager.restart('feedback:new')
  const third = manager.begin('feedback:new')

  assert.notEqual(first, second)
  assert.notEqual(second, third)
})

test('keeps keys isolated by action and entity', () => {
  let sequence = 0
  const manager = createRequestKeyManager(() => `key-${++sequence}`)
  assert.notEqual(manager.begin('binding:1'), manager.begin('binding:2'))
})

const test = require('node:test')
const assert = require('node:assert/strict')

const ENV_MODULE = '../../config/env'

test('develop environment defaults to the current LAN backend and enables mock only when explicit', () => {
  const { resolveEnvironment } = require(ENV_MODULE)

  assert.deepEqual(resolveEnvironment({ envVersion: 'develop' }), {
    envVersion: 'develop',
    apiBase: 'http://192.168.110.24:8001',
    useMock: false
  })
  assert.equal(resolveEnvironment({
    envVersion: 'develop',
    requestedMock: true
  }).useMock, true)
})

test('trial and release require an explicit HTTPS API base', () => {
  const { resolveEnvironment } = require(ENV_MODULE)

  assert.throws(
    () => resolveEnvironment({ envVersion: 'trial' }),
    /HTTPS API 地址/
  )
  assert.throws(
    () => resolveEnvironment({
      envVersion: 'release',
      apiBases: { release: 'http://api.example.test' }
    }),
    /HTTPS API 地址/
  )
})

test('non-development environments always disable mock and trim the base slash', () => {
  const { resolveEnvironment } = require(ENV_MODULE)
  const value = resolveEnvironment({
    envVersion: 'trial',
    requestedMock: true,
    apiBases: { trial: 'https://trial-api.example.test/' }
  })

  assert.deepEqual(value, {
    envVersion: 'trial',
    apiBase: 'https://trial-api.example.test',
    useMock: false
  })
})

test('unknown environment is treated as release-safe', () => {
  const { resolveEnvironment } = require(ENV_MODULE)
  const value = resolveEnvironment({
    envVersion: 'unexpected',
    requestedMock: true,
    apiBases: { release: 'https://api.example.test' }
  })

  assert.equal(value.envVersion, 'release')
  assert.equal(value.useMock, false)
})

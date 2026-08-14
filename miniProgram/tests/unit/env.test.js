const test = require('node:test')
const assert = require('node:assert/strict')

const ENV_MODULE = '../../config/env'

test('develop environment defaults to the deployed backend and enables mock only when explicit', () => {
  const { resolveEnvironment } = require(ENV_MODULE)

  assert.deepEqual(resolveEnvironment({ envVersion: 'develop' }), {
    envVersion: 'develop',
    apiBase: 'https://bjrutai.com',
    useMock: false
  })
  assert.equal(resolveEnvironment({
    envVersion: 'develop',
    requestedMock: true
  }).useMock, true)
})

test('trial and release use the configured production HTTPS API base', () => {
  const { resolveEnvironment } = require(ENV_MODULE)

  assert.equal(resolveEnvironment({ envVersion: 'trial' }).apiBase, 'https://bjrutai.com')
  assert.equal(resolveEnvironment({ envVersion: 'release' }).apiBase, 'https://bjrutai.com')
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

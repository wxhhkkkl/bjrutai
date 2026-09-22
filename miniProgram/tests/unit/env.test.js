const test = require('node:test')
const assert = require('node:assert/strict')

const ENV_MODULE = '../../config/env'

test('develop environment defaults to the local backend and enables mock only when explicit', () => {
  const { resolveEnvironment } = require(ENV_MODULE)

  assert.deepEqual(resolveEnvironment({ envVersion: 'develop' }), {
    envVersion: 'develop',
    apiBase: 'http://127.0.0.1:8000',
    useMock: false
  })
  assert.equal(resolveEnvironment({
    envVersion: 'develop',
    requestedMock: true
  }).useMock, true)
})

test('develop environment can use an explicit local storage API override', () => {
  const { DEV_API_BASE_KEY, getRuntimeEnvironment } = require(ENV_MODULE)
  const originalWx = global.wx
  global.wx = {
    getStorageSync(key) {
      return key === DEV_API_BASE_KEY ? 'https://bjrutai.com/' : false
    }
  }

  try {
    assert.equal(getRuntimeEnvironment({ envVersion: 'develop' }).apiBase, 'https://bjrutai.com')
    assert.equal(getRuntimeEnvironment({
      envVersion: 'develop',
      apiBases: { develop: 'http://127.0.0.1:8000' }
    }).apiBase, 'http://127.0.0.1:8000')
  } finally {
    if (originalWx === undefined) delete global.wx
    else global.wx = originalWx
  }
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

const test = require('node:test')
const assert = require('node:assert/strict')
const path = require('node:path')

function loadService() {
  const servicePath = path.resolve(__dirname, '../../services/banner-service.js')
  const requestPath = path.resolve(__dirname, '../../services/request-service.js')
  const originalRequest = require.cache[requestPath]
  const calls = []
  delete require.cache[servicePath]
  require.cache[requestPath] = {
    id: requestPath,
    filename: requestPath,
    loaded: true,
    exports: { request(apiPath, options = {}) { calls.push({ path: apiPath, options }); return Promise.resolve({}) } }
  }
  return {
    service: require(servicePath),
    calls,
    restore() {
      delete require.cache[servicePath]
      if (originalRequest) require.cache[requestPath] = originalRequest
      else delete require.cache[requestPath]
    }
  }
}

test('banner service uses the unauthenticated public banner contract', async () => {
  const fixture = loadService()
  try {
    await fixture.service.listBanners()
    assert.deepEqual(fixture.calls, [{ path: '/api/v1/banners', options: { auth: false } }])
  } finally {
    fixture.restore()
  }
})

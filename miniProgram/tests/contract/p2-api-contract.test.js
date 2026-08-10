const test = require('node:test')
const assert = require('node:assert/strict')
const path = require('node:path')

function load(name) {
  const servicePath = path.resolve(__dirname, `../../services/${name}-service.js`)
  const requestPath = path.resolve(__dirname, '../../services/request-service.js')
  const original = require.cache[requestPath]
  const calls = []
  delete require.cache[servicePath]
  require.cache[requestPath] = { id: requestPath, filename: requestPath, loaded: true, exports: { request(apiPath, options = {}) { calls.push({ apiPath, options }); return Promise.resolve({}) } } }
  return { service: require(servicePath), calls, restore() { delete require.cache[servicePath]; if (original) require.cache[requestPath] = original; else delete require.cache[requestPath] } }
}

test('profile service uses current-user contracts', async () => {
  const f = load('profile')
  try {
    await f.service.getProfile(); await f.service.updateProfile({ name: '新', version: 1 }); await f.service.getAvatarUploadToken({ fileName: 'a.png', contentType: 'image/png', fileSize: 10 })
    assert.deepEqual(f.calls.map((x) => [x.apiPath, x.options.method || 'GET']), [['/api/v1/me/profile', 'GET'], ['/api/v1/me/profile', 'PUT'], ['/api/v1/me/avatar/upload-token', 'POST']])
  } finally { f.restore() }
})

test('promotion service uses code, statistics and poster endpoints', async () => {
  const f = load('promotion')
  try {
    await f.service.getPromotionCode(); await f.service.getStatistics('30d'); await f.service.getPoster()
    assert.deepEqual(f.calls.map((x) => [x.apiPath, x.options.method || 'GET']), [['/api/v1/promotion-code', 'GET'], ['/api/v1/promotion-code/statistics', 'GET'], ['/api/v1/promotion-code/poster', 'GET']])
  } finally { f.restore() }
})

test('notification service lists and marks current-user notifications', async () => {
  const f = load('notification')
  try {
    await f.service.listNotifications({ unreadOnly: true }); await f.service.markRead('1'); await f.service.markAllRead()
    assert.deepEqual(f.calls.map((x) => [x.apiPath, x.options.method || 'GET']), [['/api/v1/notifications', 'GET'], ['/api/v1/notifications/1/read', 'POST'], ['/api/v1/notifications/read-all', 'POST']])
  } finally { f.restore() }
})

test('compliance service saves privacy settings without a version field', async () => {
  const f = load('compliance')
  try {
    await f.service.updatePrivacySettings({ maskSensitive: true, personalized: false })
    assert.deepEqual(f.calls, [{
      apiPath: '/api/v1/me/privacy-settings',
      options: { method: 'PUT', data: { maskSensitive: true, personalized: false } }
    }])
  } finally { f.restore() }
})

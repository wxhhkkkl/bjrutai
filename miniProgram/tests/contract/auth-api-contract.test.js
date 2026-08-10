const test = require('node:test')
const assert = require('node:assert/strict')
const path = require('node:path')

function loadAuthWithRequestStub() {
  const authPath = path.resolve(__dirname, '../../services/auth-service.js')
  const requestPath = path.resolve(__dirname, '../../services/request-service.js')
  const calls = []
  const originalRequest = require.cache[requestPath]

  delete require.cache[authPath]
  require.cache[requestPath] = {
    id: requestPath,
    filename: requestPath,
    loaded: true,
    exports: {
      request(apiPath, options = {}) {
        calls.push({ path: apiPath, options })
        if (apiPath === '/api/v1/auth/refresh') {
          return Promise.resolve({ accessToken: 'new-a', refreshToken: 'new-r' })
        }
        return Promise.resolve({})
      },
      setAuthHandlers() {}
    }
  }

  const auth = require(authPath)
  return {
    auth,
    calls,
    restore() {
      delete require.cache[authPath]
      if (originalRequest) require.cache[requestPath] = originalRequest
      else delete require.cache[requestPath]
    }
  }
}

test('auth service calls the seven mini-program auth endpoints with exact methods', async () => {
  const fixture = loadAuthWithRequestStub()
  try {
    fixture.auth.setTokens('a', 'refresh-current')
    await fixture.auth.distributorLogin('13800000000', 'password1')
    await fixture.auth.wechatLogin('wx-code')
    await fixture.auth.bindWechat('bind-code')
    await fixture.auth.getSession()
    await fixture.auth.phoneBind('phone-code')
    await fixture.auth.refreshTokens()
    await fixture.auth.logout()

    assert.deepEqual(fixture.calls.map(({ path, options }) => [path, options.method || 'GET']), [
      ['/api/v1/auth/distributor-login', 'POST'],
      ['/api/v1/auth/wechat-login', 'POST'],
      ['/api/v1/auth/bind-wechat', 'POST'],
      ['/api/v1/auth/session', 'GET'],
      ['/api/v1/auth/phone-bind', 'POST'],
      ['/api/v1/auth/refresh', 'POST'],
      ['/api/v1/auth/logout', 'POST']
    ])
    assert.deepEqual(fixture.calls[0].options.data, {
      phone: '13800000000',
      password: 'password1'
    })
    assert.equal(fixture.calls[0].options.auth, false)
    assert.deepEqual(fixture.calls[4].options.data, { code: 'phone-code' })
  } finally {
    fixture.restore()
  }
})

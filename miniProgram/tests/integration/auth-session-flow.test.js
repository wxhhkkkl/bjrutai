const test = require('node:test')
const assert = require('node:assert/strict')
const path = require('node:path')

function loadAuth(sessionResponse) {
  const authPath = path.resolve(__dirname, '../../services/auth-service.js')
  const requestPath = path.resolve(__dirname, '../../services/request-service.js')
  const sessionPath = path.resolve(__dirname, '../../services/session-service.js')
  const originalRequest = require.cache[requestPath]
  delete require.cache[authPath]
  delete require.cache[sessionPath]
  require.cache[requestPath] = {
    id: requestPath,
    filename: requestPath,
    loaded: true,
    exports: {
      request(apiPath) {
        if (apiPath === '/api/v1/auth/session') return Promise.resolve(sessionResponse)
        if (apiPath === '/api/v1/auth/logout') return Promise.resolve(null)
        return Promise.reject(new Error(`unexpected ${apiPath}`))
      },
      setAuthHandlers() {}
    }
  }
  return {
    auth: require(authPath),
    session: require(sessionPath),
    restore() {
      delete require.cache[authPath]
      delete require.cache[sessionPath]
      if (originalRequest) require.cache[requestPath] = originalRequest
      else delete require.cache[requestPath]
    }
  }
}

test('bound-user session restore replaces stale user data conservatively', async () => {
  const fixture = loadAuth({
    user: {
      userId: 'user-new',
      nickname: '最新姓名',
      phone: '139****1111',
      role: 'promoter',
      avatarUrl: '/new.png'
    },
    permissions: ['customer.read'],
    tokenExpiresAt: '2026-08-08T12:00:00+0800'
  })

  try {
    fixture.session.setAuthenticatedSession({
      accessToken: 'a',
      refreshToken: 'r',
      session: {
        userId: 'user-old',
        name: '旧姓名',
        orgRole: 'admin',
        profileCompleted: true,
        activationStatus: 'active'
      }
    })

    const restored = await fixture.auth.restoreSession()
    assert.equal(restored.userId, 'user-new')
    assert.equal(restored.name, '最新姓名')
    assert.equal(restored.orgRole, 'member')
    assert.equal(restored.permissions[0], 'customer.read')
  } finally {
    fixture.restore()
  }
})

test('logout clears real client state even when called through the flow helper', async () => {
  const fixture = loadAuth({})
  try {
    fixture.session.setAuthenticatedSession({
      accessToken: 'a',
      refreshToken: 'r',
      session: { userId: 'u', role: 'promoter' }
    })
    await fixture.auth.logoutAndClear()
    assert.equal(fixture.session.getAccessToken(), '')
    assert.equal(fixture.session.getCurrentSession().userId, '')
  } finally {
    fixture.restore()
  }
})

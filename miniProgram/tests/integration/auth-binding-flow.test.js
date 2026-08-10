const test = require('node:test')
const assert = require('node:assert/strict')
const path = require('node:path')

function loadFlow(responses) {
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
        const queue = responses[apiPath] || []
        if (!queue.length) return Promise.reject(new Error(`unexpected ${apiPath}`))
        return Promise.resolve(queue.shift())
      },
      setAuthHandlers() {}
    }
  }

  const auth = require(authPath)
  const session = require(sessionPath)
  return {
    auth,
    session,
    restore() {
      delete require.cache[authPath]
      delete require.cache[sessionPath]
      if (originalRequest) require.cache[requestPath] = originalRequest
      else delete require.cache[requestPath]
    }
  }
}

test('phone login requiring WeChat binding keeps a limited real session then completes it', async () => {
  const fixture = loadFlow({
    '/api/v1/auth/session': [{
      user: {
        userId: 'user-8',
        nickname: '测试分销员',
        phone: '138****0000',
        role: 'promoter',
        avatarUrl: ''
      },
      permissions: ['customer.read'],
      tokenExpiresAt: '2026-08-08T12:00:00+0800'
    }]
  })

  try {
    const loginResult = {
      accessToken: 'access-before-bind',
      refreshToken: 'refresh-before-bind',
      requiresWechatBinding: true,
      distributor: {
        distributorId: 'dist-8',
        orgId: 'org-1',
        orgName: '测试组织',
        orgRole: 'admin',
        name: '测试分销员',
        phone: '138****0000',
        status: 'active'
      }
    }

    const pending = await fixture.auth.establishSession(loginResult)
    assert.equal(pending.requiresWechatBinding, true)
    assert.equal(fixture.session.getCurrentSession().distributorId, 'dist-8')
    assert.equal(fixture.session.getCurrentSession().userId, '')

    fixture.auth.setTokens('access-after-bind', 'refresh-after-bind')
    const completed = await fixture.auth.restoreSession({
      preserveSession: fixture.session.getCurrentSession(),
      wechatBound: true
    })

    assert.equal(completed.userId, 'user-8')
    assert.equal(completed.distributorId, 'dist-8')
    assert.equal(completed.orgRole, 'admin')
    assert.equal(completed.wechatBound, true)
  } finally {
    fixture.restore()
  }
})

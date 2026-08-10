const test = require('node:test')
const assert = require('node:assert/strict')

const sessionService = require('../../services/session-service')
const demo = require('../../mock/demo-control')

test('stores tokens and session as one authenticated client state', () => {
  sessionService.clearAuthenticatedSession()
  sessionService.setAuthenticatedSession({
    accessToken: 'access-1',
    refreshToken: 'refresh-1',
    session: {
      userId: 'u-1',
      role: 'promoter',
      name: '测试人员',
      activationStatus: 'active',
      profileCompleted: true
    }
  })

  assert.equal(sessionService.getAccessToken(), 'access-1')
  assert.equal(sessionService.getRefreshToken(), 'refresh-1')
  assert.equal(sessionService.getCurrentSession().userId, 'u-1')
})

test('real session never falls back to demo session', () => {
  sessionService.clearAuthenticatedSession()
  demo.setDemoSession({
    userId: 'demo-user',
    role: 'promoter',
    activationStatus: 'active',
    profileCompleted: true
  })

  assert.equal(sessionService.getCurrentSession().userId, '')
})

test('logout clears tokens and account summary together', () => {
  sessionService.setAuthenticatedSession({
    accessToken: 'access-2',
    refreshToken: 'refresh-2',
    session: { userId: 'u-2', role: 'promoter' }
  })
  sessionService.clearAuthenticatedSession()

  assert.equal(sessionService.getAccessToken(), '')
  assert.equal(sessionService.getRefreshToken(), '')
  assert.equal(sessionService.getCurrentSession().userId, '')
})

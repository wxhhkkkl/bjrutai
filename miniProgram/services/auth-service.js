const sessionService = require('./session-service')
const {
  request,
  setAuthHandlers
} = require('./request-service')

function distributorLogin(phone, password) {
  return request('/api/v1/auth/distributor-login', {
    method: 'POST',
    auth: false,
    retryAfterRefresh: false,
    data: { phone, password }
  })
}

function bindWechat(code) {
  return request('/api/v1/auth/bind-wechat', {
    method: 'POST',
    data: { code }
  })
}

function distributorRegister(phone, password, name) {
  return request('/api/v1/auth/distributor-register', {
    method: 'POST',
    auth: false,
    retryAfterRefresh: false,
    data: { phone, password, name }
  })
}

function wechatLogin(code, phoneCode) {
  const data = { code }
  if (phoneCode) data.phoneCode = phoneCode
  return request('/api/v1/auth/wechat-login', {
    method: 'POST',
    auth: false,
    retryAfterRefresh: false,
    data
  })
}

function getSession() {
  return request('/api/v1/auth/session')
}

function phoneBind(code) {
  return request('/api/v1/auth/phone-bind', {
    method: 'POST',
    data: { code }
  })
}

function refreshTokens() {
  const refreshToken = sessionService.getRefreshToken()
  if (!refreshToken) return Promise.reject(new Error('刷新凭证不存在'))

  return request('/api/v1/auth/refresh', {
    method: 'POST',
    auth: false,
    retryAfterRefresh: false,
    data: { refreshToken }
  }).then((result) => {
    sessionService.setTokens(result.accessToken, result.refreshToken)
    return result
  })
}

function logout() {
  return request('/api/v1/auth/logout', {
    method: 'POST',
    retryAfterRefresh: false
  })
}

function setTokens(accessToken, refreshToken) {
  sessionService.setTokens(accessToken, refreshToken)
}

function getAccessToken() {
  return sessionService.getAccessToken()
}

function sessionFromPayload(payload, preserveSession, wechatBound) {
  const value = payload || {}
  const user = Object.assign({}, value.user, {
    permissions: value.permissions || []
  })
  const preserved = preserveSession || {}
  const distributor = {
    distributorId: preserved.distributorId,
    orgId: preserved.orgId,
    orgName: preserved.orgName || preserved.organization,
    orgRole: preserved.orgRole,
    status: preserved.activationStatus === 'inactive' ? 'disabled' : 'active'
  }
  const session = sessionService.buildDistributorSession(user, distributor)

  session.permissions = Array.isArray(value.permissions)
    ? value.permissions.slice()
    : []
  session.wechatBound = wechatBound === undefined
    ? Boolean(user.openId || preserved.wechatBound)
    : wechatBound === true
  return session
}

function restoreSession(options = {}) {
  return getSession().then((payload) => {
    const session = sessionFromPayload(
      payload,
      options.preserveSession,
      options.wechatBound
    )
    sessionService.setSession(session)
    return session
  })
}

async function establishSession(result = {}) {
  if (!result.accessToken || !result.refreshToken) {
    throw new Error('登录响应缺少访问凭证')
  }

  setTokens(result.accessToken, result.refreshToken)
  const seedSession = sessionService.buildDistributorSession(
    result.user,
    result.distributor
  )

  if (result.requiresWechatBinding) {
    seedSession.wechatBound = false
    sessionService.setSession(seedSession)
    return {
      requiresWechatBinding: true,
      isNewUser: false,
      session: seedSession
    }
  }

  if (result.user && result.user.isNewUser === true) {
    seedSession.profileCompleted = false
    seedSession.wechatBound = true
    sessionService.setSession(seedSession)
    return {
      requiresWechatBinding: false,
      isNewUser: true,
      session: seedSession
    }
  }

  const session = await restoreSession({
    preserveSession: seedSession,
    wechatBound: true
  })
  return {
    requiresWechatBinding: false,
    isNewUser: false,
    session
  }
}

async function logoutAndClear() {
  try {
    await logout()
  } finally {
    sessionService.clearAuthenticatedSession()
  }
}

function clearSessionAndReturnToLogin() {
  sessionService.clearAuthenticatedSession()
  if (typeof wx !== 'undefined' && wx.reLaunch) {
    wx.reLaunch({ url: '/pages/auth/login/index' })
  }
}

setAuthHandlers({
  refreshAccessToken: refreshTokens,
  onAuthExpired: clearSessionAndReturnToLogin
})

module.exports = {
  distributorLogin,
  distributorRegister,
  bindWechat,
  wechatLogin,
  getSession,
  phoneBind,
  refreshTokens,
  logout,
  logoutAndClear,
  establishSession,
  restoreSession,
  setTokens,
  getAccessToken
}

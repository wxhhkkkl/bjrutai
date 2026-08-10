const { getRuntimeEnvironment } = require('./config/env')
const sessionService = require('./services/session-service')

const SESSION_API_BASE_KEY = 'lutai_session_api_base'

function resetSessionWhenApiChanges(apiBase) {
  if (typeof wx === 'undefined' || !wx.getStorageSync || !wx.setStorageSync) return
  const previousBase = String(wx.getStorageSync(SESSION_API_BASE_KEY) || '').replace(/\/+$/, '')
  if (previousBase !== apiBase) {
    // Tokens are bound to the backend that issued them. This also handles
    // legacy sessions created before the API-base marker existed.
    sessionService.clearAuthenticatedSession()
  }
  wx.setStorageSync(SESSION_API_BASE_KEY, apiBase)
}

App({
  onLaunch() {
    this.globalData.launchedAt = Date.now()

    try {
      const environment = getRuntimeEnvironment()
      resetSessionWhenApiChanges(environment.apiBase)
      Object.assign(this.globalData, environment, {
        configurationError: ''
      })
    } catch (error) {
      Object.assign(this.globalData, {
        apiBase: '',
        useMock: false,
        configurationError: error.message || '小程序环境配置错误'
      })
    }
  },
  globalData: {
    launchedAt: 0,
    envVersion: 'develop',
    apiBase: '',
    useMock: false,
    configurationError: ''
  }
})

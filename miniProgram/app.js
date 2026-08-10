const { getRuntimeEnvironment } = require('./config/env')

App({
  onLaunch() {
    this.globalData.launchedAt = Date.now()

    try {
      const environment = getRuntimeEnvironment()
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

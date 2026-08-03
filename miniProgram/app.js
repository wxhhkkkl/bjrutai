App({
  onLaunch() {
    this.globalData.launchedAt = Date.now()
  },
  globalData: {
    launchedAt: 0,
    // 后端地址：微信开发者工具勾选「不校验合法域名」后，本机调试可用 127.0.0.1。
    apiBase: 'http://127.0.0.1:8000'
  }
})

App({
  onLaunch() {
    this.globalData.launchedAt = Date.now()
  },
  globalData: {
    launchedAt: 0
  }
})

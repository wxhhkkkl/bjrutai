const echarts = require('../../ec-canvas/echarts')
const customerService = require('../../services/customer-service')
const {
  CUSTOMER_ANALYSIS_TABS,
  adaptCustomerAnalysis,
  getBindingDistribution
} = require('../../models/customer-analysis')

function buildTrendOption(period) {
  return {
    animationDuration: 650,
    grid: { top: 38, right: 14, bottom: 4, left: 5, containLabel: true },
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', boundaryGap: false, data: period.trend.categories },
    yAxis: { type: 'value', min: 0, max: period.trend.max, interval: period.trend.interval },
    series: [{
      type: 'line', smooth: 0, showSymbol: true, symbol: 'circle', symbolSize: 9,
      data: period.trend.values,
      lineStyle: { color: '#1677ff', width: 3 },
      itemStyle: { color: '#ffffff', borderColor: '#1677ff', borderWidth: 2 },
      areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
        { offset: 0, color: 'rgba(22, 119, 255, 0.25)' },
        { offset: 1, color: 'rgba(22, 119, 255, 0.01)' }
      ]) }
    }]
  }
}

function buildStatusOption(period) {
  return {
    animationDuration: 600,
    series: [{
      type: 'pie', radius: ['58%', '78%'], center: ['50%', '50%'], silent: true,
      label: { show: false }, labelLine: { show: false },
      data: getBindingDistribution(period).map((item) => ({
        value: item.value, name: item.name, itemStyle: { color: item.color }
      }))
    }]
  }
}

function errorState(error) {
  return error && error.kind === 'FORBIDDEN' ? 'forbidden' : 'recoverable-error'
}

Page({
  requestVersion: 0,
  data: {
    state: 'loading',
    stateMessage: '',
    periods: CUSTOMER_ANALYSIS_TABS,
    selectedPeriod: 'month',
    period: null,
    distribution: [],
    selectedDate: '2026-08-08',
    ec: { lazyLoad: true }
  },

  onReady() {
    this.trendComponent = this.selectComponent('#customer-trend-chart')
    this.statusComponent = this.selectComponent('#binding-status-chart')
    this.loadAnalysis('month')
  },

  onShow() {
    if (this.trendChart) this.trendChart.resize()
    if (this.statusChart) this.statusChart.resize()
  },

  onUnload() {
    this.requestVersion += 1
    if (this.trendChart) this.trendChart.dispose()
    if (this.statusChart) this.statusChart.dispose()
  },

  async loadAnalysis(selectedPeriod) {
    const version = ++this.requestVersion
    const tab = CUSTOMER_ANALYSIS_TABS.find((item) => item.id === selectedPeriod) || CUSTOMER_ANALYSIS_TABS[0]
    this.setData({ state: 'loading', stateMessage: '', selectedPeriod })
    try {
      const adapted = adaptCustomerAnalysis(await customerService.getCustomerAnalysis(tab.apiPeriod))
      if (version !== this.requestVersion) return
      this.setData({ state: 'success', period: adapted, distribution: getBindingDistribution(adapted) })
      this.updateCharts(adapted)
    } catch (error) {
      if (version !== this.requestVersion) return
      this.setData({ state: errorState(error), stateMessage: error.message || '请稍后再试' })
    }
  },

  updateCharts(period) {
    if (!this.trendChart) this.initTrendChart(period)
    else this.trendChart.setOption(buildTrendOption(period), true)
    if (!this.statusChart) this.initStatusChart(period)
    else this.statusChart.setOption(buildStatusOption(period), true)
  },

  initTrendChart(period) {
    if (!this.trendComponent || this.trendChart) return
    this.trendComponent.init((canvas, width, height, dpr) => {
      const chart = echarts.init(canvas, null, { width, height, devicePixelRatio: dpr })
      canvas.setChart(chart)
      chart.setOption(buildTrendOption(period))
      this.trendChart = chart
      return chart
    })
  },

  initStatusChart(period) {
    if (!this.statusComponent || this.statusChart) return
    this.statusComponent.init((canvas, width, height, dpr) => {
      const chart = echarts.init(canvas, null, { width, height, devicePixelRatio: dpr })
      canvas.setChart(chart)
      chart.setOption(buildStatusOption(period))
      this.statusChart = chart
      return chart
    })
  },

  selectPeriod(e) {
    const selectedPeriod = e.currentTarget.dataset.id
    if (selectedPeriod !== this.data.selectedPeriod) this.loadAnalysis(selectedPeriod)
  },

  onDateChange(e) {
    this.setData({ selectedDate: e.detail.value })
  },

  openAttention(e) {
    if (e.currentTarget.dataset.type === 'matching') {
      wx.navigateTo({ url: '/pages/binding-records/index?filter=matching' })
      return
    }
    wx.switchTab({ url: '/pages/customers/index' })
  },

  retry() {
    this.loadAnalysis(this.data.selectedPeriod)
  },

  handleBack() {
    wx.navigateBack()
  }
})

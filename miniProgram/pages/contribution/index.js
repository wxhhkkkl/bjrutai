const echarts = require('../../ec-canvas/echarts')
const consumptionService = require('../../services/consumption-service')
const { adaptContributionOverview, adaptContributionTrend, adaptBillList } = require('../../models/contribution-detail')
const { updateTabBar, openAction } = require('../../services/navigation-service')
const { getCurrentSession } = require('../../services/session-service')

const PERIODS = [{ id: 'month', label: '本月', api: '3m' }, { id: 'quarter', label: '近3月', api: '6m' }, { id: 'year', label: '本年', api: '12m' }]
function currentMonth() { const now = new Date(); return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}` }
function chartOption(trend) {
  const interval = Math.max(trend.interval, trend.max / 4)
  return {
    grid: { left: 52, right: 16, top: 20, bottom: 28, containLabel: true },
    xAxis: { type: 'category', data: trend.categories },
    yAxis: {
      type: 'value', min: 0, max: trend.max, interval,
      axisLabel: { margin: 9, color: '#8a8f98' },
      splitNumber: 4
    },
    series: [{ type: 'line', smooth: true, data: trend.values, lineStyle: { color: '#1677ff', width: 3 }, areaStyle: { color: 'rgba(22,119,255,.15)' } }]
  }
}
function errorState(error) { return error && error.kind === 'FORBIDDEN' ? 'forbidden' : 'recoverable-error' }

Page({
  requestVersion: 0,
  data: { state: 'loading', stateMessage: '', overview: {}, details: [], hasTrendData: false, hasDetails: false, periods: PERIODS, selectedPeriod: 'month', chartSummary: { label: '本月累计', total: '—' }, ec: { lazyLoad: true } },
  onShow() { updateTabBar(this, 'contribution'); this.loadData('month') },
  onReady() { this.chartComponent = this.selectComponent('#contribution-trend-chart'); if (this.data.hasTrendData) this.renderTrendChart(this.data.trend) },
  onUnload() { this.requestVersion += 1; if (this.chart) this.chart.dispose() },

  renderTrendChart(trend) {
    if (!trend || !trend.values.length) return
    if (!this.chartComponent) this.chartComponent = this.selectComponent('#contribution-trend-chart')
    if (!this.chartComponent) return
    if (!this.chart) this.chartComponent.init((canvas, width, height, dpr) => { const chart = echarts.init(canvas, null, { width, height, devicePixelRatio: dpr }); canvas.setChart(chart); chart.setOption(chartOption(trend)); this.chart = chart; return chart })
    else this.chart.setOption(chartOption(trend), true)
  },

  async loadData(periodId = this.data.selectedPeriod) {
    const version = ++this.requestVersion; const period = PERIODS.find((item) => item.id === periodId) || PERIODS[0]; const month = currentMonth()
    this.setData({ state: 'loading', selectedPeriod: periodId })
    try {
      const [overviewPayload, trendPayload, billsPayload] = await Promise.all([consumptionService.getOverview(month), consumptionService.getTrend(period.api), consumptionService.listBills({ month, pageSize: 5 })])
      if (version !== this.requestVersion) return
      const overview = adaptContributionOverview(overviewPayload); const trend = adaptContributionTrend(trendPayload); const bills = adaptBillList(billsPayload)
      const hasTrendData = trend.values.some((value) => value !== 0)
      this.setData({ state: 'success', overview, details: bills.items, hasTrendData, hasDetails: bills.items.length > 0, chartSummary: { label: `${period.label}累计`, total: overview.amount }, trend }, () => {
        if (hasTrendData) this.renderTrendChart(trend)
      })
      if (!hasTrendData) {
        if (this.chart) { this.chart.dispose(); this.chart = null }
      }
    } catch (error) { if (version === this.requestVersion) this.setData({ state: errorState(error), stateMessage: error.message || '请稍后再试' }) }
  },
  retry() { this.loadData(this.data.selectedPeriod) },
  selectPeriod(e) { const id = e.currentTarget.dataset.id; if (id !== this.data.selectedPeriod) this.loadData(id) },
  openAllDetails() { this.openActionPage('contribution-detail') },
  openDetail() { wx.showToast({ title: '账单详情暂不可用，请以消费列表为准', icon: 'none' }) },
  openActionPage(actionId) { const result = openAction(actionId, getCurrentSession()); if (result.ok) wx.navigateTo({ url: result.url }); else wx.showToast({ title: result.message, icon: 'none' }) }
})

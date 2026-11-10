const consumptionService = require('../../services/consumption-service')
const { formatCents, adaptContributionOverview, adaptContributionTrend, adaptBillList } = require('../../models/contribution-detail')
const { openAction } = require('../../services/navigation-service')
const { getCurrentSession } = require('../../services/session-service')

const PERIODS = [{ id: 'month', label: '本月', api: '1m' }, { id: 'quarter', label: '近3月', api: '3m' }, { id: 'year', label: '本年' }]
function currentMonth() { const now = new Date(); return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}` }
function errorState(error) { return error && error.kind === 'FORBIDDEN' ? 'forbidden' : 'recoverable-error' }

Page({
  requestVersion: 0,
  data: { state: 'loading', stateMessage: '', overview: {}, details: [], hasTrendData: false, hasDetails: false, periods: PERIODS, selectedPeriod: 'month', chartSummary: { label: '本月累计', total: '—' }, trend: { categories: [], values: [], max: 0, interval: 0 } },
  onShow() { this.loadData('month') },
  onUnload() { this.requestVersion += 1 },
  handleBack() { wx.navigateBack() },

  async loadData(periodId = this.data.selectedPeriod) {
    const version = ++this.requestVersion; const period = PERIODS.find((item) => item.id === periodId) || PERIODS[0]; const month = currentMonth()
    const trendPeriod = period.id === 'year' ? `${Number(month.slice(5))}m` : period.api
    this.setData({ state: 'loading', selectedPeriod: periodId })
    try {
      const [overviewPayload, trendPayload, billsPayload] = await Promise.all([consumptionService.getOverview(month), consumptionService.getTrend(trendPeriod), consumptionService.listBills({ month, pageSize: 5 })])
      if (version !== this.requestVersion) return
      const overview = adaptContributionOverview(overviewPayload); const trend = adaptContributionTrend(trendPayload); const bills = adaptBillList(billsPayload)
      const hasTrendData = trend.values.some((value) => value !== 0)
      const trendTotalCent = trend.values.reduce((total, value) => total + value, 0)
      this.setData({ state: 'success', overview, details: bills.items, hasTrendData, hasDetails: bills.items.length > 0, chartSummary: { label: `${period.label}累计`, total: formatCents(trendTotalCent) }, trend })
    } catch (error) { if (version === this.requestVersion) this.setData({ state: errorState(error), stateMessage: error.message || '请稍后再试' }) }
  },
  retry() { this.loadData(this.data.selectedPeriod) },
  selectPeriod(e) { const id = e.currentTarget.dataset.id; if (id !== this.data.selectedPeriod) this.loadData(id) },
  openAllDetails() { this.openActionPage('contribution-detail') },
  openActionPage(actionId) { const result = openAction(actionId, getCurrentSession()); if (result.ok) wx.navigateTo({ url: result.url }); else wx.showToast({ title: result.message, icon: 'none' }) }
})

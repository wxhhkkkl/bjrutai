const consumptionService = require('../../services/consumption-service')
const { adaptContributionOverview, adaptBillList } = require('../../models/contribution-detail')

const FILTERS = [
  { id: 'all', label: '全部' },
  { id: 'paid', label: '已支付' },
  { id: 'partially_refunded', label: '部分退款' },
  { id: 'refunded', label: '已退款' },
  { id: 'cancelled', label: '已取消' }
]

function currentMonth() {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
}

function monthLabel(value) {
  const [year, month] = String(value).split('-')
  return `${year}年${Number(month)}月`
}

function displayDate(value) {
  if (!value) return '未知日期'
  const date = new Date(value)
  return `${date.getMonth() + 1}月${date.getDate()}日`
}

function buildGroups(records) {
  const groups = []
  records.forEach((record) => {
    const date = displayDate(record.occurredAt)
    const last = groups[groups.length - 1]
    if (last && last.date === date) last.items.push({ ...record, time: String(record.occurredAt || '').replace('T', ' ').slice(11, 16) })
    else groups.push({ date, items: [{ ...record, time: String(record.occurredAt || '').replace('T', ' ').slice(11, 16) }] })
  })
  return groups
}

Page({
  requestVersion: 0,
  data: {
    state: 'loading', stateMessage: '', monthValue: currentMonth(),
    month: { label: monthLabel(currentMonth()), total: '0.00', totalCount: 0, settledCount: 0 },
    filters: FILTERS.map((item) => ({ ...item, count: 0 })),
    selectedStatus: 'all', records: [], groups: []
  },

  onLoad() { this.loadData() },
  handleBack() { wx.navigateBack() },

  async loadData() {
    const version = ++this.requestVersion
    const monthValue = this.data.monthValue
    this.setData({ state: 'loading', stateMessage: '' })
    try {
      const [overviewPayload, billsPayload] = await Promise.all([
        consumptionService.getOverview(monthValue),
        consumptionService.listBills({ month: monthValue, pageSize: 100 })
      ])
      if (version !== this.requestVersion) return
      const overview = adaptContributionOverview(overviewPayload)
      const records = adaptBillList(billsPayload).items
      const counts = Object.fromEntries(FILTERS.map((item) => [item.id, item.id === 'all' ? records.length : records.filter((record) => record.status === item.id).length]))
      const visible = this.data.selectedStatus === 'all' ? records : records.filter((record) => record.status === this.data.selectedStatus)
      this.setData({
        state: 'success', month: { label: monthLabel(monthValue), total: overview.amount.replace(/^¥/, ''), totalCount: counts.all, settledCount: counts.paid },
        filters: FILTERS.map((item) => ({ ...item, count: counts[item.id] })), records, groups: buildGroups(visible)
      })
    } catch (error) {
      if (version === this.requestVersion) this.setData({ state: error.kind === 'FORBIDDEN' ? 'forbidden' : 'recoverable-error', stateMessage: error.message || '消费数据加载失败，请稍后重试' })
    }
  },

  retry() { this.loadData() },
  onMonthChange(event) { this.setData({ monthValue: event.detail.value, selectedStatus: 'all' }); this.loadData() },
  selectStatus(event) {
    const selectedStatus = event.currentTarget.dataset.id
    const items = this.data.records
    const visible = selectedStatus === 'all' ? items : items.filter((record) => record.status === selectedStatus)
    this.setData({ selectedStatus, groups: buildGroups(visible) })
  },
  async openContribution(event) {
    try {
      const detail = await consumptionService.getBillDetail(event.currentTarget.dataset.id)
      wx.showModal({
        title: detail.title || '消费记录',
        content: `客户：${detail.customerName || '未知客户'}\n金额：¥${(Number(detail.amountCent || 0) / 100).toFixed(2)}\n状态：${detail.status === 'paid' ? '已支付' : detail.status === 'partially_refunded' ? '部分退款' : detail.status === 'refunded' ? '已退款' : '已取消'}`,
        showCancel: false, confirmText: '知道了'
      })
    } catch (error) { wx.showToast({ title: error.message || '消费详情加载失败', icon: 'none' }) }
  }
})

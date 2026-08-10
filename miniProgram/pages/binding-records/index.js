const bindingService = require('../../services/binding-service')
const { adaptBindingRecords, adaptBindingSummary, filterBindingRecords, sortBindingRecords } = require('../../models/binding-records')

const FILTERS = [{ id: 'all', label: '全部' }, { id: 'bound', label: '已绑定' }, { id: 'matching', label: '待匹配' }, { id: 'processing', label: '处理中' }]

Page({
  requestVersion: 0,
  data: { state: 'loading', stateMessage: '', summary: [], filters: FILTERS, records: [], visibleRecords: [], selectedFilter: 'all', selectedCount: 0, keyword: '', sortMode: 'recent', nextCursor: '', hasMore: false },

  onLoad(options = {}) { this.setData({ selectedFilter: FILTERS.some((item) => item.id === options.filter) ? options.filter : 'all' }); this.loadRecords(true) },
  onUnload() { this.requestVersion += 1 },

  async loadRecords(reset = false) {
    const version = ++this.requestVersion
    this.setData({ state: reset ? 'loading' : this.data.state })
    try {
      const [recordPayload, summaryPayload] = await Promise.all([bindingService.listBindingRequests({ status: this.data.selectedFilter === 'all' ? undefined : this.data.selectedFilter === 'matching' ? 'pending_match' : this.data.selectedFilter, submittedByMe: true, keyword: this.data.keyword, cursor: reset ? undefined : this.data.nextCursor, limit: 20 }), bindingService.getBindingSummary()])
      if (version !== this.requestVersion) return
      const adapted = adaptBindingRecords(recordPayload)
      const records = reset ? adapted.items : this.data.records.concat(adapted.items)
      const summary = adaptBindingSummary(summaryPayload)
      this.setData({ state: 'success', records, visibleRecords: this.getVisibleRecords(records), nextCursor: adapted.nextCursor, hasMore: adapted.hasMore, selectedCount: records.length, summary: [{ id: 'bound', label: '已绑定', count: summary.bound, icon: 'contact-o', tone: 'green' }, { id: 'matching', label: '待匹配', count: summary.pending, icon: 'clock-o', tone: 'blue' }, { id: 'processing', label: '处理中', count: summary.rejected + summary.expired, icon: 'replay', tone: 'orange' }] })
    } catch (error) { if (version === this.requestVersion) this.setData({ state: error.kind === 'FORBIDDEN' ? 'forbidden' : 'recoverable-error', stateMessage: error.message || '请稍后再试' }) }
  },
  retry() { this.loadRecords(true) },
  getVisibleRecords(records = this.data.records, overrides = {}) { const filter = overrides.selectedFilter || this.data.selectedFilter; const keyword = overrides.keyword === undefined ? this.data.keyword : overrides.keyword; const sort = overrides.sortMode || this.data.sortMode; return sortBindingRecords(filterBindingRecords(records, filter, keyword), sort) },
  onSearch(e) { this.setData({ keyword: e.detail.value }); this.loadRecords(true) },
  selectFilter(e) { this.setData({ selectedFilter: e.currentTarget.dataset.id, records: [], visibleRecords: [] }); this.loadRecords(true) },
  openSort() { wx.showActionSheet({ itemList: ['按最近提交排序', '按客户姓名排序', '优先显示处理中'], success: ({ tapIndex }) => { const sortMode = ['recent', 'name', 'status'][tapIndex] || 'recent'; this.setData({ sortMode, visibleRecords: this.getVisibleRecords(this.data.records, { sortMode }) }) } }) },
  showStatusDescription() { wx.showModal({ title: '状态说明', content: '绑定状态由后端匹配服务更新。', showCancel: false }) },
  openRecord() { wx.showToast({ title: '详情重试和审计信息暂不可用', icon: 'none' }) },
  continueBinding() { wx.navigateTo({ url: '/pages/customer-binding/index' }) },
  handleBack() { wx.navigateBack() }
})

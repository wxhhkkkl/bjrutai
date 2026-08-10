const {
  FOLLOWUP_METHODS,
  FOLLOWUP_RESULTS,
  formatFollowupDate,
  validateFollowupRecord
} = require('../../models/followup-record')
const customerService = require('../../services/customer-service')

Page({
  data: {
    customer: {},
    methods: FOLLOWUP_METHODS,
    results: FOLLOWUP_RESULTS,
    saving: false,
    form: {
      method: 'phone', result: 'connected', content: '', reminderEnabled: true,
      reminderDate: '', reminderTime: ''
    },
    contentLength: 0,
    reminderDateText: ''
  },

  async onLoad(options = {}) {
    const id = options.id || ''
    this.setData({ customer: { id } })
    if (!id) return
    try {
      const customer = await customerService.getCustomer(id)
      this.setData({ customer: { id, name: customer.name || '', phone: customer.phoneMasked || customer.phone || '', contributionAvatar: '/assets/images/customer-avatar-blue.png' } })
    } catch (error) { wx.showToast({ title: error.message || '客户信息加载失败', icon: 'none' }) }
  },

  selectMethod(e) {
    this.setData({ 'form.method': e.currentTarget.dataset.id })
  },

  selectResult(e) {
    this.setData({ 'form.result': e.currentTarget.dataset.id })
  },

  onContentInput(e) {
    const content = e.detail.value
    this.setData({ 'form.content': content, contentLength: content.length })
  },

  toggleReminder() {
    this.setData({ 'form.reminderEnabled': !this.data.form.reminderEnabled })
  },

  onReminderDateChange(e) {
    const reminderDate = e.detail.value
    this.setData({ 'form.reminderDate': reminderDate, reminderDateText: formatFollowupDate(reminderDate) })
  },

  onReminderTimeChange(e) {
    this.setData({ 'form.reminderTime': e.detail.value })
  },

  async saveDraft() {
    if (this.data.saving || !this.data.customer.id) return
    this.setData({ saving: true })
    try {
      await customerService.saveFollowupDraft(this.data.customer.id, { method: this.data.form.method, content: String(this.data.form.content || '').trim() })
      wx.showToast({ title: '草稿已保存', icon: 'success' })
    } catch (error) { wx.showToast({ title: error.message || '草稿保存失败', icon: 'none' }) } finally { this.setData({ saving: false }) }
  },

  async saveFollowup() {
    const result = validateFollowupRecord(this.data.form)
    if (!result.valid) {
      wx.showToast({ title: result.message, icon: 'none' })
      return
    }
    if (this.data.saving || !this.data.customer.id) return
    this.setData({ saving: true })
    try {
      const reminderAt = result.value.reminderEnabled ? `${result.value.reminderDate}T${result.value.reminderTime}:00` : null
      const method = result.value.method === 'in-person' ? 'visit' : result.value.method
      const resultMap = { connected: 'successful', waiting: 'pending', unanswered: 'no_answer' }
      await customerService.createFollowup(this.data.customer.id, { method, result: resultMap[result.value.result], content: result.value.content, reminderAt })
      wx.showToast({ title: '跟进已保存', icon: 'success' })
      setTimeout(() => wx.navigateBack(), 500)
    } catch (error) { wx.showToast({ title: error.message || '跟进保存失败', icon: 'none' }) } finally { this.setData({ saving: false }) }
  },

  handleBack() {
    wx.navigateBack()
  }
})

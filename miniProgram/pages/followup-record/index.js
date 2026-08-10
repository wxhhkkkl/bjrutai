const {
  FOLLOWUP_METHODS,
  FOLLOWUP_RESULTS,
  formatFollowupDate,
  validateFollowupRecord
} = require('../../models/followup-record')

const BLOCKED_MESSAGE = '跟进接口当前缺少可确认的客户归属权限，暂不能提交。'

Page({
  data: {
    customer: {},
    methods: FOLLOWUP_METHODS,
    results: FOLLOWUP_RESULTS,
    blockedMessage: BLOCKED_MESSAGE,
    form: {
      method: 'phone', result: 'connected', content: '', reminderEnabled: true,
      reminderDate: '', reminderTime: ''
    },
    contentLength: 0,
    reminderDateText: ''
  },

  onLoad(options = {}) {
    this.setData({ customer: { id: options.id || '' } })
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

  saveDraft() {
    wx.showToast({ title: this.data.blockedMessage, icon: 'none' })
  },

  saveFollowup() {
    const result = validateFollowupRecord(this.data.form)
    if (!result.valid) {
      wx.showToast({ title: result.message, icon: 'none' })
      return
    }
    wx.showToast({ title: this.data.blockedMessage, icon: 'none' })
  },

  handleBack() {
    wx.navigateBack()
  }
})

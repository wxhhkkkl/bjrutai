const { getCustomerDetail } = require('../../models/customer-detail');
const {
  FOLLOWUP_METHODS,
  FOLLOWUP_RESULTS,
  formatFollowupDate,
  validateFollowupRecord
} = require('../../models/followup-record');

Page({
  data: {
    customer: getCustomerDetail('customer-001'),
    methods: FOLLOWUP_METHODS,
    results: FOLLOWUP_RESULTS,
    form: {
      method: 'phone',
      result: 'connected',
      content: '',
      reminderEnabled: true,
      reminderDate: '2026-07-23',
      reminderTime: '16:00'
    },
    contentLength: 0,
    reminderDateText: '2026年7月23日'
  },

  onLoad(options = {}) {
    this.setData({
      customer: getCustomerDetail(options.id)
    });
  },

  selectMethod(e) {
    this.setData({
      'form.method': e.currentTarget.dataset.id
    });
  },

  selectResult(e) {
    this.setData({
      'form.result': e.currentTarget.dataset.id
    });
  },

  onContentInput(e) {
    const content = e.detail.value;

    this.setData({
      'form.content': content,
      contentLength: content.length
    });
  },

  toggleReminder() {
    this.setData({
      'form.reminderEnabled': !this.data.form.reminderEnabled
    });
  },

  onReminderDateChange(e) {
    const reminderDate = e.detail.value;

    this.setData({
      'form.reminderDate': reminderDate,
      reminderDateText: formatFollowupDate(reminderDate)
    });
  },

  onReminderTimeChange(e) {
    this.setData({
      'form.reminderTime': e.detail.value
    });
  },

  saveDraft() {
    wx.showToast({
      title: '草稿已保存',
      icon: 'success'
    });
  },

  saveFollowup() {
    const result = validateFollowupRecord(this.data.form);

    if (!result.valid) {
      wx.showToast({
        title: result.message,
        icon: 'none'
      });
      return;
    }

    this.setData({ form: result.value });
    wx.showToast({
      title: '跟进已保存',
      icon: 'success'
    });
  },

  handleBack() {
    wx.navigateBack();
  }
});

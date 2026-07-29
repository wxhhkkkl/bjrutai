const {
  MAX_CONTENT_LENGTH,
  MAX_SCREENSHOTS,
  HELP_FAQS,
  FEEDBACK_TYPES,
  validateFeedback,
  createFeedbackRecord
} = require('../../models/help-feedback');

const FEEDBACK_STORAGE_KEY = 'lutai_feedback_records';

Page({
  data: {
    faqs: HELP_FAQS,
    feedbackTypes: FEEDBACK_TYPES,
    selectedType: 'issue',
    content: '',
    contentLength: 0,
    maxContentLength: MAX_CONTENT_LENGTH,
    images: [],
    maxScreenshots: MAX_SCREENSHOTS,
    invalidField: '',
    submitting: false
  },

  handleBack() {
    if (getCurrentPages().length > 1) {
      wx.navigateBack({ delta: 1 });
      return;
    }

    wx.switchTab({
      url: '/pages/profile/index'
    });
  },

  openFaq(event) {
    const faq = this.data.faqs.find(
      (item) => item.id === event.currentTarget.dataset.id
    );

    if (!faq) return;
    wx.showModal({
      title: faq.title,
      content: faq.answer,
      showCancel: false,
      confirmText: '知道了'
    });
  },

  selectFeedbackType(event) {
    this.setData({
      selectedType: event.currentTarget.dataset.id,
      invalidField: ''
    });
  },

  onContentInput(event) {
    const content = event.detail.value;

    this.setData({
      content,
      contentLength: content.length,
      invalidField: ''
    });
  },

  chooseScreenshots() {
    const remaining = MAX_SCREENSHOTS - this.data.images.length;

    if (remaining <= 0) {
      wx.showToast({
        title: `最多上传 ${MAX_SCREENSHOTS} 张截图`,
        icon: 'none'
      });
      return;
    }

    if (!wx.chooseMedia) {
      wx.showToast({
        title: '当前微信版本暂不支持图片选择',
        icon: 'none'
      });
      return;
    }

    wx.chooseMedia({
      count: remaining,
      mediaType: ['image'],
      sourceType: ['album', 'camera'],
      sizeType: ['compressed'],
      success: ({ tempFiles }) => {
        const selected = (tempFiles || [])
          .map((item) => item.tempFilePath)
          .filter(Boolean);

        this.setData({
          images: this.data.images.concat(selected).slice(0, MAX_SCREENSHOTS),
          invalidField: ''
        });
      }
    });
  },

  previewScreenshot(event) {
    const current = event.currentTarget.dataset.src;

    wx.previewImage({
      current,
      urls: this.data.images
    });
  },

  removeScreenshot(event) {
    const index = Number(event.currentTarget.dataset.index);
    const images = this.data.images.slice();

    if (Number.isNaN(index)) return;
    images.splice(index, 1);
    this.setData({ images });
  },

  handleContact() {
    wx.showToast({
      title: '已进入客服会话',
      icon: 'none'
    });
  },

  submitFeedback() {
    const payload = {
      type: this.data.selectedType,
      content: this.data.content,
      images: this.data.images
    };
    const validation = validateFeedback(payload);

    if (!validation.valid) {
      this.setData({
        invalidField: validation.field
      });
      wx.showToast({
        title: validation.message,
        icon: 'none'
      });
      return;
    }

    if (this.data.submitting) return;
    this.setData({
      submitting: true,
      invalidField: ''
    });

    const records = wx.getStorageSync(FEEDBACK_STORAGE_KEY) || [];
    records.unshift(createFeedbackRecord(payload));
    wx.setStorageSync(FEEDBACK_STORAGE_KEY, records);

    wx.showModal({
      title: '反馈已提交',
      content: '感谢您的反馈，我们会尽快处理并通过消息通知您。',
      showCancel: false,
      confirmText: '完成',
      success: () => {
        this.setData({ submitting: false });
        this.handleBack();
      }
    });
  }
});

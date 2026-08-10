const feedbackService = require('../../services/feedback-service')
const profileService = require('../../services/profile-service')
const { MAX_CONTENT_LENGTH, MAX_SCREENSHOTS, HELP_FAQS, FEEDBACK_TYPES, validateFeedback } = require('../../models/help-feedback')

Page({
  data: { faqs: HELP_FAQS, feedbackTypes: FEEDBACK_TYPES, selectedType: 'issue', content: '', contentLength: 0, maxContentLength: MAX_CONTENT_LENGTH, images: [], imageFiles: [], maxScreenshots: MAX_SCREENSHOTS, invalidField: '', submitting: false, uploadingImages: false },
  handleBack() { if (getCurrentPages().length > 1) wx.navigateBack({ delta: 1 }); else wx.switchTab({ url: '/pages/profile/index' }) },
  openFaq(event) { const faq = this.data.faqs.find((item) => item.id === event.currentTarget.dataset.id); if (faq) wx.showModal({ title: faq.title, content: faq.answer, showCancel: false }) },
  selectFeedbackType(event) { this.setData({ selectedType: event.currentTarget.dataset.id, invalidField: '' }) },
  onContentInput(event) { this.setData({ content: event.detail.value, contentLength: event.detail.value.length, invalidField: '' }) },
  chooseScreenshots() {
    if (this.data.uploadingImages) return
    const remaining = this.data.maxScreenshots - this.data.images.length
    if (remaining <= 0) return

    wx.chooseImage({
      count: remaining,
      sizeType: ['compressed', 'original'],
      sourceType: ['album', 'camera'],
      success: async ({ tempFilePaths = [], tempFiles = [] }) => {
        if (!tempFilePaths.length) return
        this.setData({ uploadingImages: true, invalidField: '' })
        try {
          const uploads = await Promise.all(tempFilePaths.map((filePath, index) => (
            profileService.uploadAvatar(filePath, tempFiles[index] || {})
          )))
          const fileIds = uploads.map((upload) => upload && upload.fileId).filter(Boolean)
          if (fileIds.length !== tempFilePaths.length) throw new Error('图片上传结果异常，请重试')
          this.setData({
            images: this.data.images.concat(tempFilePaths),
            imageFiles: this.data.imageFiles.concat(fileIds),
            uploadingImages: false
          })
        } catch (error) {
          this.setData({ uploadingImages: false })
          wx.showToast({ title: error.message || '图片上传失败，请重试', icon: 'none' })
        }
      },
      fail: (error) => {
        if (!error || !String(error.errMsg || '').includes('cancel')) wx.showToast({ title: '选择图片失败，请重试', icon: 'none' })
      }
    })
  },
  previewScreenshot(event) {
    const current = event.currentTarget.dataset.src
    if (current && wx.previewImage) wx.previewImage({ current, urls: this.data.images })
  },
  removeScreenshot(event) {
    const index = Number(event.currentTarget.dataset.index)
    if (!Number.isInteger(index) || index < 0) return
    const images = this.data.images.slice()
    const imageFiles = this.data.imageFiles.slice()
    images.splice(index, 1)
    imageFiles.splice(index, 1)
    this.setData({ images, imageFiles })
  },
  async submitFeedback() {
    const validation = validateFeedback({ type: this.data.selectedType, content: this.data.content, images: this.data.images })
    if (!validation.valid) { this.setData({ invalidField: validation.field }); wx.showToast({ title: validation.message, icon: 'none' }); return }
    if (this.data.submitting) return
    this.setData({ submitting: true, invalidField: '' })
    try { await feedbackService.submitFeedback({ type: this.data.selectedType === 'issue' ? 'bug' : this.data.selectedType, content: this.data.content, imageFiles: this.data.imageFiles, contactAllowed: false }); wx.showModal({ title: '反馈已提交', content: '感谢您的反馈。', showCancel: false, success: () => this.handleBack() }) } catch (error) { wx.showToast({ title: error.message || '提交失败，请稍后重试', icon: 'none' }) } finally { this.setData({ submitting: false }) }
  }
})

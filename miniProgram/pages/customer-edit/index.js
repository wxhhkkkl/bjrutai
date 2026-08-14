const customerService = require('../../services/customer-service')
const { adaptCustomerDetail } = require('../../models/customer-detail')
const {
  EDITABLE_CUSTOMER_FIELDS,
  createCustomerEditForm,
  validateEditField,
  validateCustomerEditForm,
  adaptCustomerEditResponse
} = require('../../models/customer-edit')

const BLOCKED_FIELDS = new Set(['idCard', 'medicalAccount'])

Page({
  data: {
    state: 'loading',
    stateMessage: '',
    customer: {},
    isBound: false,
    form: createCustomerEditForm({}),
    originalForm: createCustomerEditForm({}),
    noteLength: 0,
    editorVisible: false,
    editorField: '',
    editorTitle: '',
    editorValue: '',
    editorType: 'text',
    editorMaxlength: 30,
    editorSensitive: false
  },

  onLoad(options = {}) {
    this.customerId = options.id || ''
    this.loadCustomer()
  },

  async loadCustomer() {
    this.setData({ state: 'loading', stateMessage: '' })
    try {
      const customer = adaptCustomerDetail(await customerService.getCustomer(this.customerId))
      const form = createCustomerEditForm(customer)
      this.setData({
        state: 'success',
        customer,
        form,
        originalForm: Object.assign({}, form),
        isBound: customer.statusCode === 'bound',
        noteLength: String(form.note || '').length
      })
    } catch (error) {
      this.setData({ state: error.kind === 'FORBIDDEN' ? 'forbidden' : 'recoverable-error', stateMessage: error.message || '请稍后再试' })
    }
  },

  retry() {
    this.loadCustomer()
  },

  openEditor(e) {
    const field = e.currentTarget.dataset.field
    if (this.data.isBound && field !== 'name') {
      wx.showToast({ title: '客户绑定后仅允许修改姓名', icon: 'none' })
      return
    }
    if (BLOCKED_FIELDS.has(field)) {
      wx.showToast({ title: '该敏感字段暂不支持前端修改', icon: 'none' })
      return
    }
    const config = EDITABLE_CUSTOMER_FIELDS[field]
    if (!config) return
    this.setData({
      editorVisible: true,
      editorField: field,
      editorTitle: config.title,
      editorValue: this.data.form[field],
      editorType: config.type,
      editorMaxlength: config.maxlength,
      editorSensitive: config.sensitive
    })
  },

  onEditorInput(e) {
    this.setData({ editorValue: e.detail.value })
  },

  confirmEditor() {
    const result = validateEditField(this.data.editorField, this.data.editorValue)
    if (!result.valid) {
      wx.showToast({ title: result.message, icon: 'none' })
      return
    }
    this.setData({ [`form.${this.data.editorField}`]: result.value, editorVisible: false })
  },

  closeEditor() {
    this.setData({ editorVisible: false })
  },

  onNoteInput(e) {
    if (this.data.isBound) return
    const note = e.detail.value
    this.setData({ 'form.note': note, noteLength: note.length })
  },

  async saveChanges() {
    const result = validateCustomerEditForm(this.data.form)
    if (!result.valid) {
      wx.showToast({ title: result.message, icon: 'none' })
      return
    }
    const original = this.data.originalForm
    if (result.value.phone !== original.phone) {
      wx.showToast({ title: '修改手机号需要后端 changeReason，当前页面暂不提交', icon: 'none' })
      return
    }

    const payload = this.data.isBound
      ? { name: result.value.name }
      : {
        name: result.value.name,
        note: result.value.note,
        familyPhone: result.value.familyPhone
      }
    try {
      const response = await customerService.patchCustomer(this.customerId, payload)
      const updated = adaptCustomerEditResponse(response)
      this.setData({
        form: Object.assign({}, this.data.form, updated),
        originalForm: Object.assign({}, this.data.form, updated),
        customer: Object.assign({}, this.data.customer, updated)
      })
      wx.showToast({ title: '资料已更新', icon: 'success' })
    } catch (error) {
      wx.showToast({ title: error.message || '保存失败，请稍后重试', icon: 'none' })
    }
  },

  cancelEdit() {
    wx.navigateBack()
  },

  handleBack() {
    wx.navigateBack()
  }
})

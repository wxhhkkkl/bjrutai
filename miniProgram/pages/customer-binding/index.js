const { getCurrentSession } = require('../../services/session-service')
const bindingService = require('../../services/binding-service')
const { createRequestKeyManager } = require('../../utils/request-key')
const { openAction } = require('../../services/navigation-service')
const { validateCustomerForm, maskPhone, maskIdCard, formatBindingTime } = require('../../models/customer-binding')
const { getIdentityLabel } = require('../../models/collaborator')

const INITIAL_FORM = { name: '', phone: '', idCard: '', medicalAccount: '', familyPhone: '' }
const STEP_TITLES = ['客户绑定', '确认绑定', '绑定结果']

Page({
  requestVersion: 0,
  data: { step: 1, navTitle: STEP_TITLES[0], form: { ...INITIAL_FORM }, invalidField: '', owner: {}, promoters: [], maskedPhone: '', maskedIdCard: '', bindingTime: '', state: 'loading', stateMessage: '' },

  onLoad() {
    const session = getCurrentSession()
    this.keyManager = createRequestKeyManager()
    this.setData({ owner: { name: session.name || '', roleLabel: getIdentityLabel(session) } })
    this.loadBindingOptions()
  },

  async loadBindingOptions() {
    const version = ++this.requestVersion
    try {
      const promoterPayload = await bindingService.getSelectablePromoters({ limit: 20 })
      if (version !== this.requestVersion) return
      const promoters = require('../../models/customer-binding').adaptSelectablePromoters(promoterPayload).items
      this.setData({ state: 'success', promoters })
    } catch (error) {
      if (version !== this.requestVersion) return
      this.setData({ state: error.kind === 'FORBIDDEN' ? 'forbidden' : 'recoverable-error', stateMessage: error.message || '暂时无法加载绑定配置' })
    }
  },

  retry() { this.loadBindingOptions() },
  onInput(e) { this.setData({ [`form.${e.currentTarget.dataset.field}`]: e.detail.value, invalidField: '' }) },

  nextStep() {
    const result = validateCustomerForm(this.data.form)
    if (!result.valid) { this.setData({ invalidField: result.field }); wx.showToast({ title: result.message, icon: 'none' }); return }
    if (!this.data.owner.id) { wx.showToast({ title: '请选择归属拓展人', icon: 'none' }); return }
    this.setData({ form: result.value, maskedPhone: maskPhone(result.value.phone), maskedIdCard: maskIdCard(result.value.idCard) })
    this.setStep(2)
  },

  selectOwner() {
    if (!this.data.promoters.length) { wx.showToast({ title: '暂无可选拓展人', icon: 'none' }); return }
    wx.showActionSheet({ itemList: this.data.promoters.map((item) => item.name), success: ({ tapIndex }) => { const item = this.data.promoters[tapIndex]; if (item) this.setData({ owner: { ...item, roleLabel: '鲁泰拓展人' } }) } })
  },
  goToStepOne() { this.setStep(1) },
  async submitBinding() {
    const flowId = `binding:${this.data.form.phone}`
    const key = this.keyManager.begin(flowId)
    this.setData({ state: 'loading' })
    try {
      const result = await bindingService.submitBinding({ promoterId: this.data.owner.id, promoterCode: this.data.owner.code, customerInfo: this.data.form }, key)
      this.keyManager.markSucceeded(flowId)
      this.setData({ state: 'success', bindingTime: result.submittedAt ? String(result.submittedAt).replace('T', ' ').slice(0, 16) : formatBindingTime(), resultState: result.status })
      this.setStep(3)
    } catch (error) {
      this.keyManager.markUnknown(flowId)
      this.setData({ state: 'recoverable-error', stateMessage: error.message || '提交结果未知，请到绑定记录确认' })
      wx.showToast({ title: error.message || '提交失败，请到绑定记录确认', icon: 'none' })
    }
  },

  continueBinding() { this.setData({ form: { ...INITIAL_FORM }, invalidField: '', maskedPhone: '', maskedIdCard: '', bindingTime: '', step: 1, navTitle: STEP_TITLES[0] }) },
  handleBack() { if (this.data.step === 2) this.setStep(1); else wx.navigateBack() },
  setStep(step) { this.setData({ step, navTitle: STEP_TITLES[step - 1] }); wx.pageScrollTo({ scrollTop: 0, duration: 180 }) },
  openBindingRecords() { this.openActionPage('binding-records') },
  completeCustomerInfo() { wx.showToast({ title: '请在客户详情中继续完善', icon: 'none' }) },
  openActionPage(actionId) { const result = openAction(actionId, getCurrentSession()); if (result.ok) wx.navigateTo({ url: result.url }); else wx.showToast({ title: result.message, icon: 'none' }) }
})

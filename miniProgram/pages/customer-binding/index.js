const { getCurrentSession } = require('../../services/session-service');
const {
  openAction
} = require('../../services/navigation-service');
const {
  validateCustomerForm,
  maskPhone,
  maskIdCard,
  formatBindingTime
} = require('../../models/customer-binding');
const {
  getIdentityLabel
} = require('../../models/collaborator');

const INITIAL_FORM = {
  name: '',
  phone: '',
  idCard: '',
  medicalAccount: '',
  familyPhone: ''
};

const STEP_TITLES = ['客户绑定', '确认绑定', '绑定结果'];

Page({
  data: {
    step: 1,
    navTitle: STEP_TITLES[0],
    form: { ...INITIAL_FORM },
    invalidField: '',
    owner: {
      name: '张小明',
      roleLabel: '鲁泰协作人员'
    },
    authorized: true,
    maskedPhone: '',
    maskedIdCard: '',
    bindingTime: ''
  },

  onLoad() {
    const session = getCurrentSession();

    this.setData({
      owner: {
        name: session.name || '张小明',
        roleLabel: getIdentityLabel(session)
      }
    });
  },

  onInput(e) {
    const field = e.currentTarget.dataset.field;
    const value = e.detail.value;

    this.setData({
      [`form.${field}`]: value,
      invalidField: ''
    });
  },

  nextStep() {
    const result = validateCustomerForm(this.data.form);

    if (!result.valid) {
      this.setData({ invalidField: result.field });
      wx.showToast({ title: result.message, icon: 'none' });
      return;
    }

    this.setData({
      form: result.value,
      maskedPhone: maskPhone(result.value.phone),
      maskedIdCard: maskIdCard(result.value.idCard)
    });
    this.setStep(2);
  },

  selectOwner() {
    wx.showActionSheet({
      itemList: [`${this.data.owner.name}（已激活）`]
    });
  },

  goToStepOne() {
    this.setStep(1);
  },

  toggleAuthorization() {
    this.setData({ authorized: !this.data.authorized });
  },

  submitBinding() {
    if (!this.data.authorized) {
      wx.showToast({
        title: '请先确认已获得客户明确授权',
        icon: 'none'
      });
      return;
    }

    this.setData({ bindingTime: formatBindingTime() });
    this.setStep(3);
  },

  continueBinding() {
    this.setData({
      form: { ...INITIAL_FORM },
      invalidField: '',
      authorized: true,
      maskedPhone: '',
      maskedIdCard: '',
      bindingTime: ''
    });
    this.setStep(1);
  },

  handleBack() {
    if (this.data.step === 2) {
      this.setStep(1);
      return;
    }

    wx.navigateBack();
  },

  setStep(step) {
    this.setData({
      step,
      navTitle: STEP_TITLES[step - 1]
    });

    wx.pageScrollTo({
      scrollTop: 0,
      duration: 180
    });
  },

  openPrivacy() {
    this.openActionPage('privacy');
  },

  openBindingRecords() {
    this.openActionPage('binding-records');
  },

  completeCustomerInfo() {
    wx.navigateTo({
      url: '/pages/customer-edit/index?id=customer-001'
    });
  },

  openActionPage(actionId) {
    const result = openAction(actionId, getCurrentSession());

    if (result.ok) {
      wx.navigateTo({ url: result.url });
    } else {
      wx.showToast({ title: result.message, icon: 'none' });
    }
  }
});

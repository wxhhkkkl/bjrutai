const {
  CUSTOMER_DETAIL_TABS,
  CONTRIBUTION_FILTERS,
  SERVICE_RECORDS,
  CONTRIBUTION_RECORDS,
  normalizeCustomerDetailTab,
  getCustomerDetail,
  filterContributionRecords
} = require('../../models/customer-detail');

Page({
  data: {
    tabs: CUSTOMER_DETAIL_TABS,
    currentTab: 'info',
    customer: getCustomerDetail('customer-001'),
    heroAvatar: '/assets/images/customer-avatar-purple.png',
    services: SERVICE_RECORDS,
    contributionFilters: CONTRIBUTION_FILTERS,
    selectedContributionFilter: 'all',
    contributions: CONTRIBUTION_RECORDS
  },

  onLoad(options = {}) {
    const currentTab = normalizeCustomerDetailTab(options.tab);
    const customer = getCustomerDetail(options.id);

    this.setData({
      currentTab,
      customer,
      heroAvatar: currentTab === 'contribution'
        ? customer.contributionAvatar
        : customer.avatar
    });
  },

  selectTab(e) {
    const currentTab = normalizeCustomerDetailTab(
      e.currentTarget.dataset.id
    );

    this.setData({
      currentTab,
      heroAvatar: currentTab === 'contribution'
        ? this.data.customer.contributionAvatar
        : this.data.customer.avatar
    });

    wx.pageScrollTo({
      scrollTop: 0,
      duration: 180
    });
  },

  selectContributionFilter(e) {
    const selectedContributionFilter = e.currentTarget.dataset.id;

    this.setData({
      selectedContributionFilter,
      contributions: filterContributionRecords(
        CONTRIBUTION_RECORDS,
        selectedContributionFilter
      )
    });
  },

  editCustomer() {
    wx.navigateTo({
      url: `/pages/customer-edit/index?id=${this.data.customer.id}`
    });
  },

  openBindingRecords() {
    wx.navigateTo({ url: '/pages/binding-records/index' });
  },

  openService(e) {
    const service = this.data.services.find(
      (item) => item.id === e.currentTarget.dataset.id
    );

    if (!service) return;

    if (service.status === '待跟进') {
      this.openFollowupRecord();
      return;
    }

    wx.showToast({
      title: '该服务已完成',
      icon: 'none'
    });
  },

  contactCustomer() {
    wx.showModal({
      title: `联系${this.data.customer.name}`,
      content: `客户手机号：${this.data.customer.phone}`,
      showCancel: false,
      confirmText: '我知道了'
    });
  },

  recordFollowup() {
    this.openFollowupRecord();
  },

  openFollowupRecord() {
    wx.navigateTo({
      url: `/pages/followup-record/index?id=${this.data.customer.id}`
    });
  },

  handleBack() {
    wx.navigateBack();
  }
});

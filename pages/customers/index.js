const { summaries } = require('../../mock/foundation-fixtures');
const demo = require('../../mock/demo-control');
const {
  updateTabBar,
  openAction
} = require('../../services/navigation-service');
const { getCurrentSession } = require('../../services/session-service');
const {
  filterCustomers,
  sortCustomers
} = require('../../models/customer-list');

const FILTERS = [
  { id: 'all', label: '全部', count: 36 },
  { id: 'matching', label: '待匹配', count: 3 },
  { id: 'followup', label: '待跟进', count: 8 }
];

Page({
  data: {
    state: 'success',
    list: [],
    visibleList: [],
    filters: FILTERS,
    selectedFilter: 'all',
    keyword: '',
    sortMode: 'recent'
  },

  onShow() {
    const list = summaries.customers;

    this.setData({
      state: demo.getPageViewState('customers'),
      list,
      visibleList: this.getVisibleList(list)
    });
    updateTabBar(this, 'customers');
  },

  getVisibleList(list = this.data.list, overrides = {}) {
    const selectedFilter = overrides.selectedFilter
      || this.data.selectedFilter;
    const keyword = overrides.keyword === undefined
      ? this.data.keyword
      : overrides.keyword;
    const sortMode = overrides.sortMode || this.data.sortMode;

    return sortCustomers(
      filterCustomers(list, selectedFilter, keyword),
      sortMode
    );
  },

  retry() {
    demo.setPageViewState('customers', 'success');
    this.onShow();
  },

  onSearch(e) {
    const keyword = e.detail.value;

    this.setData({
      keyword,
      visibleList: this.getVisibleList(this.data.list, { keyword })
    });
  },

  selectFilter(e) {
    const selectedFilter = e.currentTarget.dataset.id;

    this.setData({
      selectedFilter,
      visibleList: this.getVisibleList(this.data.list, { selectedFilter })
    });
  },

  openSort() {
    wx.showActionSheet({
      itemList: ['按最近服务排序', '按姓名排序'],
      success: ({ tapIndex }) => {
        const sortMode = tapIndex === 1 ? 'name' : 'recent';

        this.setData({
          sortMode,
          visibleList: this.getVisibleList(this.data.list, { sortMode })
        });
      }
    });
  },

  openAnalysis() {
    this.openActionPage('customer-analysis');
  },

  bindCustomer() {
    this.openActionPage('bind-client');
  },

  openActionPage(actionId) {
    const result = openAction(actionId, getCurrentSession());

    if (result.ok) {
      wx.navigateTo({ url: result.url });
    } else {
      wx.showToast({ title: result.message, icon: 'none' });
    }
  },

  openCustomer(e) {
    const id = e.currentTarget.dataset.id;

    wx.navigateTo({
      url: `/pages/customer-detail/index?id=${id}`
    });
  }
});

const {
  BINDING_SUMMARY,
  BINDING_FILTERS,
  BINDING_RECORDS,
  filterBindingRecords,
  sortBindingRecords
} = require('../../models/binding-records');

Page({
  data: {
    summary: BINDING_SUMMARY,
    filters: BINDING_FILTERS,
    records: BINDING_RECORDS,
    visibleRecords: BINDING_RECORDS,
    selectedFilter: 'all',
    selectedCount: 36,
    keyword: '',
    sortMode: 'recent'
  },

  onLoad(options = {}) {
    const selectedFilter = this.data.filters.some(
      (item) => item.id === options.filter
    )
      ? options.filter
      : 'all';
    const selected = this.data.filters.find(
      (item) => item.id === selectedFilter
    );

    this.setData({
      selectedFilter,
      selectedCount: selected ? selected.count : 36,
      visibleRecords: this.getVisibleRecords({ selectedFilter })
    });
  },

  getVisibleRecords(overrides = {}) {
    const selectedFilter = overrides.selectedFilter
      || this.data.selectedFilter;
    const keyword = overrides.keyword === undefined
      ? this.data.keyword
      : overrides.keyword;
    const sortMode = overrides.sortMode || this.data.sortMode;

    return sortBindingRecords(
      filterBindingRecords(this.data.records, selectedFilter, keyword),
      sortMode
    );
  },

  onSearch(e) {
    const keyword = e.detail.value;

    this.setData({
      keyword,
      visibleRecords: this.getVisibleRecords({ keyword })
    });
  },

  selectFilter(e) {
    const selectedFilter = e.currentTarget.dataset.id;
    const selected = this.data.filters.find(
      (filter) => filter.id === selectedFilter
    );

    this.setData({
      selectedFilter,
      selectedCount: selected ? selected.count : 0,
      visibleRecords: this.getVisibleRecords({ selectedFilter })
    });
  },

  openSort() {
    wx.showActionSheet({
      itemList: ['按最近提交排序', '按客户姓名排序', '优先显示处理中'],
      success: ({ tapIndex }) => {
        const modes = ['recent', 'name', 'status'];
        const sortMode = modes[tapIndex] || 'recent';

        this.setData({
          sortMode,
          visibleRecords: this.getVisibleRecords({ sortMode })
        });
      }
    });
  },

  showStatusDescription() {
    wx.showModal({
      title: '状态说明',
      content: '已绑定：客户归属已确认。\n待匹配：系统正在匹配儒泰用户。\n处理中：异常任务正在自动重试。',
      showCancel: false,
      confirmText: '我知道了'
    });
  },

  openRecord(e) {
    const record = this.data.records.find(
      (item) => item.id === e.currentTarget.dataset.id
    );

    if (!record) return;

    wx.navigateTo({
      url: `/pages/binding-result/index?id=${record.id}`
    });
  },

  continueBinding() {
    wx.navigateTo({ url: '/pages/customer-binding/index' });
  },

  handleBack() {
    wx.navigateBack();
  }
});

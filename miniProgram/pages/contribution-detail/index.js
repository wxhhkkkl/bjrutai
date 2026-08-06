const {
  CONTRIBUTION_MONTHS,
  CONTRIBUTION_RECORDS,
  getContributionMonth,
  getStatusFilters,
  filterContributionDetails,
  groupContributionDetails
} = require('../../models/contribution-detail');

Page({
  data: {
    monthValue: CONTRIBUTION_MONTHS[0].id,
    month: CONTRIBUTION_MONTHS[0],
    filters: getStatusFilters(CONTRIBUTION_MONTHS[0]),
    selectedStatus: 'all',
    selectedCategory: 'all',
    groups: groupContributionDetails(
      filterContributionDetails(CONTRIBUTION_RECORDS, {
        month: CONTRIBUTION_MONTHS[0].id,
        status: 'all',
        category: 'all'
      })
    )
  },

  getVisibleGroups(overrides = {}) {
    const month = overrides.month || this.data.monthValue;
    const status = overrides.status || this.data.selectedStatus;
    const category = overrides.category || this.data.selectedCategory;

    return groupContributionDetails(
      filterContributionDetails(CONTRIBUTION_RECORDS, {
        month,
        status,
        category
      })
    );
  },

  onMonthChange(e) {
    const monthValue = e.detail.value;
    const month = getContributionMonth(monthValue);

    this.setData({
      monthValue: month.id,
      month,
      filters: getStatusFilters(month),
      selectedStatus: 'all',
      selectedCategory: 'all',
      groups: this.getVisibleGroups({
        month: month.id,
        status: 'all',
        category: 'all'
      })
    });
  },

  selectStatus(e) {
    const selectedStatus = e.currentTarget.dataset.id;

    this.setData({
      selectedStatus,
      groups: this.getVisibleGroups({ status: selectedStatus })
    });
  },

  openContribution(e) {
    const record = CONTRIBUTION_RECORDS.find(
      (item) => item.id === e.currentTarget.dataset.id
    );

    if (!record) return;

    wx.showModal({
      title: record.title,
      content: `${record.customer} · ${record.phone}\n${record.date} ${record.time}\n消费 ¥${record.points} · ${record.statusLabel}`,
      showCancel: false,
      confirmText: '我知道了'
    });
  },

  handleBack() {
    wx.navigateBack();
  }
});

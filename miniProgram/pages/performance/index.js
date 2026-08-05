/**
 * 我的绩效（008, US3）
 * 展示当月提成预估 + 历史已确认月份（审核确认后冻结）。
 */
const { requestMyCommission } = require('../../services/commission-service');

function fmtYuan(cent) {
  const num = Number(cent) || 0;
  return (num / 100).toFixed(2);
}
function fmtRatio(ratio) {
  return `${(Number(ratio) * 100).toFixed(2)}%`;
}

Page({
  data: {
    state: 'loading',
    currentMonth: null,
    confirmed: [],
  },

  onShow() {
    this.load();
  },

  async load() {
    try {
      const data = await requestMyCommission({});
      this.setData({
        state: 'success',
        currentMonth: data.currentMonth || null,
        confirmed: data.confirmed || [],
      });
    } catch {
      this.setData({ state: 'recoverable-error' });
    }
  },

  retry() {
    this.setData({ state: 'loading' });
    this.load();
  },

  handleBack() {
    wx.navigateBack({ delta: 1 });
  },

  fmtYuan,
  fmtRatio,
});

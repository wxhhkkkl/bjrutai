/**
 * 我的绩效（008, US3）
 * 展示当月提成预估 + 历史已确认月份（审核确认后冻结）。
 */
const { requestMyCommission } = require('../../services/commission-service');
const { formatYuan } = require('../../utils/money');

function fmtYuan(cent) {
  return formatYuan(Number.isSafeInteger(cent) ? cent : 0, { symbol: false });
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

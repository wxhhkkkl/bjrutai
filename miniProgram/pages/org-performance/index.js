const { getCurrentSession } = require('../../services/session-service');
const { requestOrgPerformance } = require('../../services/org-performance-service');

const MONTHS = ['2026-07', '2026-08', '2026-09'];

function formatNumber(value) {
  const num = Number(value);
  return Number.isFinite(num) ? num.toLocaleString('en-US') : '0';
}

Page({
  data: {
    state: 'loading',
    orgName: '',
    period: '',
    summary: { thisMonth: 0, cumulative: 0 },
    subOrgs: [],
    members: [],
    months: MONTHS,
    selectedMonth: MONTHS[1],
  },

  onLoad() {
    this.load();
  },

  async load() {
    const session = getCurrentSession();

    // US4/US5: only org admins (backend-authorized) may view org performance.
    if (session.orgRole !== 'admin') {
      this.setData({ state: 'forbidden' });
      return;
    }

    try {
      const data = await requestOrgPerformance({ month: this.data.selectedMonth });
      this.setData({
        state: 'success',
        orgName: data.orgName,
        period: data.period,
        summary: data.summary,
        subOrgs: data.subOrgs || [],
        members: data.members || [],
      });
    } catch {
      this.setData({ state: 'recoverable-error' });
    }
  },

  retry() {
    this.setData({ state: 'loading' });
    this.load();
  },

  selectMonth(event) {
    const month = event.currentTarget.dataset.month;
    if (!month || month === this.data.selectedMonth) return;
    this.setData({ selectedMonth: month, state: 'loading' });
    this.load();
  },

  handleBack() {
    wx.navigateBack({ delta: 1 });
  },

  formatNumber,
});

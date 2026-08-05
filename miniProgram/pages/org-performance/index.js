const { getCurrentSession } = require('../../services/session-service');
const { requestOrgPerformance } = require('../../services/org-performance-service');
const { requestOrgCommission } = require('../../services/commission-service');

const MONTHS = ['2026-07', '2026-08', '2026-09'];

function formatNumber(value) {
  const num = Number(value);
  return Number.isFinite(num) ? num.toLocaleString('en-US') : '0';
}

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
    orgName: '',
    period: '',
    summary: { thisMonth: 0, cumulative: 0 },
    subOrgs: [],
    members: [],
    months: MONTHS,
    selectedMonth: MONTHS[1],
    commission: null,
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

    // 008 US3: commission estimate + confirmed months (best-effort; failure hides the block).
    try {
      const commission = await requestOrgCommission({ month: this.data.selectedMonth });
      this.setData({ commission });
    } catch {
      this.setData({ commission: null });
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
  fmtYuan,
  fmtRatio,
});

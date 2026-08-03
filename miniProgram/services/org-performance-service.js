/**
 * Org performance API service (US5).
 *
 * Fetches the org-admin's authorized org subtree contribution summary from
 * the backend. Set USE_MOCK = true to run the demo without a backend.
 */
const USE_MOCK = false;

const MOCK_PERFORMANCE = {
  orgId: 'org_1001',
  orgName: '北京儒泰总部',
  period: '2026-08',
  summary: { thisMonth: 125000, cumulative: 860000 },
  subOrgs: [
    { orgId: 'org_1002', orgName: '华北区', thisMonth: 52000, cumulative: 310000 },
    { orgId: 'org_1003', orgName: '华东区', thisMonth: 48000, cumulative: 290000 },
  ],
  members: [
    { distributorId: 'd_1001', orgId: 'org_1002', name: '张三', thisMonth: 23000, cumulative: 150000 },
    { distributorId: 'd_1002', orgId: 'org_1002', name: '李四', thisMonth: 18000, cumulative: 96000 },
    { distributorId: 'd_1003', orgId: 'org_1003', name: '王五', thisMonth: 21000, cumulative: 112000 },
  ],
};

const { getAccessToken } = require('./auth-service');

function requestOrgPerformance({ month } = {}) {
  if (USE_MOCK) {
    return Promise.resolve({
      ...MOCK_PERFORMANCE,
      period: month || MOCK_PERFORMANCE.period,
    });
  }

  const apiBase = getApp().globalData.apiBase || 'http://127.0.0.1:8000';
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${apiBase}/api/v1/org/performance`,
      method: 'GET',
      data: { month },
      header: { Authorization: `Bearer ${getAccessToken()}` },
      success: (res) => {
        const body = res.data || {};
        if (body.code === 0) resolve(body.data);
        else reject(new Error(body.message || '获取组织业绩失败'));
      },
      fail: () => reject(new Error('网络异常，请稍后重试')),
    });
  });
}

module.exports = { requestOrgPerformance };

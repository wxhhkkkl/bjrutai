/**
 * Auth API service (T052 / FR-027).
 *
 * Distributor phone+password login and first-login WeChat binding. Backend
 * endpoints live under /api/v1/auth/. Set USE_MOCK = true to run the demo
 * without a backend.
 */
const USE_MOCK = false;

const TOKEN_KEY = 'lutai_access_token';
const REFRESH_KEY = 'lutai_refresh_token';

const MOCK_LOGIN = {
  accessToken: 'mock-access-token',
  refreshToken: 'mock-refresh-token',
  expiresIn: 7200,
  tokenType: 'Bearer',
  requiresWechatBinding: false,
  distributor: {
    distributorId: '1001',
    orgId: '1001',
    orgName: '北京儒泰总部',
    orgRole: 'admin',
    name: '张小明',
    phone: '138****1028',
    status: 'active',
  },
};

function getApiBase() {
  return getApp().globalData.apiBase || 'http://127.0.0.1:8000';
}

function request(path, { method = 'GET', data, token } = {}) {
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${getApiBase()}${path}`,
      method,
      data,
      header: token ? { Authorization: `Bearer ${token}` } : {},
      success: (res) => {
        const body = res.data || {};
        if (res.statusCode >= 400 || (body.code !== undefined && body.code !== 0)) {
          reject(new Error(body.message || `请求失败 (${res.statusCode})`));
          return;
        }
        resolve(body.data !== undefined ? body.data : body);
      },
      fail: () => reject(new Error('网络异常，请检查后端服务是否启动')),
    });
  });
}

function distributorLogin(phone, password) {
  if (USE_MOCK) {
    return Promise.resolve({ ...MOCK_LOGIN });
  }
  return request('/api/v1/auth/distributor-login', {
    method: 'POST',
    data: { phone, password },
  });
}

function bindWechat(code, token) {
  if (USE_MOCK) {
    return Promise.resolve({ bound: true, openId: 'mock-openid' });
  }
  return request('/api/v1/auth/bind-wechat', {
    method: 'POST',
    data: { code },
    token,
  });
}

function wechatLogin(code) {
  if (USE_MOCK) {
    return Promise.resolve({ ...MOCK_LOGIN });
  }
  return request('/api/v1/auth/wechat-login', {
    method: 'POST',
    data: { code },
  });
}

function getSession(token) {
  return request('/api/v1/auth/session', { token });
}

function setTokens(accessToken, refreshToken) {
  wx.setStorageSync(TOKEN_KEY, accessToken || '');
  wx.setStorageSync(REFRESH_KEY, refreshToken || '');
}

function getAccessToken() {
  return wx.getStorageSync(TOKEN_KEY) || '';
}

module.exports = {
  distributorLogin,
  bindWechat,
  wechatLogin,
  getSession,
  setTokens,
  getAccessToken,
};

const DEFAULT_PRIVACY_SETTINGS = Object.freeze({
  maskSensitive: true,
  personalized: false
});

const PRIVACY_DOCUMENTS = Object.freeze([
  {
    id: 'agreement',
    title: '用户协议',
    content: '本协议用于说明鲁泰协作服务的使用规则、账号责任及双方权利义务。使用服务前，请确认您已阅读并理解相关条款。'
  },
  {
    id: 'privacy',
    title: '隐私政策',
    content: '我们遵循合法、正当、必要和诚信原则处理个人信息，并采取合理安全措施保护您的数据。'
  },
  {
    id: 'collection',
    title: '个人信息收集清单',
    content: '为完成账号识别、客户协作和服务记录，我们可能收集微信身份、授权手机号、业务资料及您主动提交的信息。'
  },
  {
    id: 'sharing',
    title: '第三方信息共享清单',
    content: '仅在提供必要服务、履行法定义务或取得明确授权的情况下，我们才会按清单向第三方共享必要信息。'
  }
]);

function createPrivacySettings(source) {
  return Object.assign({}, DEFAULT_PRIVACY_SETTINGS, source || {});
}

function getAuthorizationView(session, systemSettings) {
  const value = session || {};
  const system = systemSettings || {};
  const phoneAuthorized = value.phoneAuthorized === true || Boolean(value.userId);
  const mediaAuthorized = system.camera !== false && system.album !== false;
  const customerMessageAuthorized = system.customerMessage === true;

  return {
    wechatBound: Boolean(value.userId),
    wechatLabel: value.userId ? '已绑定' : '未绑定',
    phone: value.phone || '138****1028',
    phoneAuthorized,
    phoneLabel: phoneAuthorized ? '已授权' : '未授权',
    mediaAuthorized,
    mediaLabel: mediaAuthorized ? '已授权' : '未授权',
    customerMessageAuthorized,
    customerMessageLabel: customerMessageAuthorized ? '已授权' : '未授权'
  };
}

function getPrivacyDocument(id) {
  return PRIVACY_DOCUMENTS.find((item) => item.id === id) || null;
}

module.exports = {
  DEFAULT_PRIVACY_SETTINGS,
  PRIVACY_DOCUMENTS,
  createPrivacySettings,
  getAuthorizationView,
  getPrivacyDocument
};

const PROMOTION_CODE = Object.freeze({
  sourceCity: '北京',
  available: true,
  qrImage: ''
});
const {
  getIdentityLabel
} = require('./collaborator');

const PROMOTION_STEPS = Object.freeze([
  {
    id: 'scan',
    icon: 'scan',
    label: '客户扫描二维码'
  },
  {
    id: 'open',
    icon: 'miniprogram-o',
    label: '进入儒泰小程序'
  },
  {
    id: 'confirm',
    icon: 'friends-o',
    label: '授权手机号并完成归属'
  }
]);

function getPromotionProfile(session = {}) {
  return {
    ...PROMOTION_CODE,
    id: session.userId || '',
    name: session.name || '',
    roleLabel: getIdentityLabel(session),
    statusLabel: PROMOTION_CODE.available ? '客户绑定码可用' : '客户绑定码已停用'
  };
}

function createPromotionShare(profile, shareConfig) {
  const value = profile || getPromotionProfile();
  const config = shareConfig || {};
  const fallbackPath = `/pages/patient-binding/index?refToken=${encodeURIComponent(value.refToken || '')}`;
  const configuredPath = config.landingPath
    ? config.landingPath.replace('{refToken}', encodeURIComponent(value.refToken || ''))
    : '';

  return {
    title: config.friendTitle || '儒泰医联｜您的专属健康服务入口',
    path: configuredPath || value.sharePath || fallbackPath,
    imageUrl: config.friendImageUrl || '/assets/images/promotion-share-friend-v1.jpg'
  };
}

module.exports = {
  PROMOTION_CODE,
  PROMOTION_STEPS,
  getPromotionProfile,
  createPromotionShare
};

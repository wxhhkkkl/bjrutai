const MAX_CONTENT_LENGTH = 500;
const MAX_SCREENSHOTS = 3;

const HELP_FAQS = Object.freeze([
  {
    id: 'binding',
    title: '客户绑定与匹配',
    icon: 'link-o',
    answer: '录入客户信息并确认授权后，系统会自动完成客户归属匹配。待匹配记录可在绑定记录页查看最新状态。'
  },
  {
    id: 'contribution',
    title: '贡献值与结算',
    icon: 'bar-chart-o',
    answer: '客户绑定、服务完成等有效行为会形成贡献值，最终结果以系统同步的实际结算数据为准。'
  },
  {
    id: 'qualification',
    title: '资质审核',
    icon: 'shield-o',
    answer: '提交完整有效的资质资料后会进入审核流程，审核结果和驳回原因可在资质状态页查看。'
  },
  {
    id: 'account',
    title: '账号与登录',
    icon: 'idcard',
    answer: '账号通过微信身份和授权手机号识别。姓名、机构和头像可在账号信息页更新。'
  }
]);

const FEEDBACK_TYPES = Object.freeze([
  {
    id: 'issue',
    label: '功能异常'
  },
  {
    id: 'suggestion',
    label: '产品建议'
  },
  {
    id: 'other',
    label: '其他'
  }
]);

function normalizeFeedbackType(type) {
  return FEEDBACK_TYPES.some((item) => item.id === type)
    ? type
    : 'issue';
}

function validateFeedback(input) {
  const value = input || {};
  const content = String(value.content || '').trim();

  if (!FEEDBACK_TYPES.some((item) => item.id === value.type)) {
    return {
      valid: false,
      field: 'type',
      message: '请选择反馈类型'
    };
  }

  if (content.length < 10) {
    return {
      valid: false,
      field: 'content',
      message: '请至少输入 10 个字的问题描述'
    };
  }

  if (content.length > MAX_CONTENT_LENGTH) {
    return {
      valid: false,
      field: 'content',
      message: `问题描述不能超过 ${MAX_CONTENT_LENGTH} 个字`
    };
  }

  if ((value.images || []).length > MAX_SCREENSHOTS) {
    return {
      valid: false,
      field: 'images',
      message: `最多上传 ${MAX_SCREENSHOTS} 张截图`
    };
  }

  return {
    valid: true
  };
}

function createFeedbackRecord(input, createdAt) {
  const value = input || {};
  const timestamp = Number(createdAt) || Date.now();

  return {
    id: `feedback-${timestamp}`,
    type: normalizeFeedbackType(value.type),
    content: String(value.content || '').trim(),
    images: (value.images || []).slice(0, MAX_SCREENSHOTS),
    status: 'submitted',
    createdAt: timestamp
  };
}

module.exports = {
  MAX_CONTENT_LENGTH,
  MAX_SCREENSHOTS,
  HELP_FAQS,
  FEEDBACK_TYPES,
  normalizeFeedbackType,
  validateFeedback,
  createFeedbackRecord
};

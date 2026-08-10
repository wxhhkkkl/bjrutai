const PHONE_PATTERN = /^1\d{10}$/;
const ID_CARD_PATTERN = /(^\d{15}$)|(^\d{17}[\dXx]$)/;

function compact(value) {
  return String(value || '').replace(/\s+/g, '');
}

function validateCustomerForm(form) {
  const value = form || {};
  const name = String(value.name || '').trim();
  const phone = compact(value.phone);
  const idCard = compact(value.idCard);
  const familyPhone = compact(value.familyPhone);

  if (!name) {
    return { valid: false, field: 'name', message: '请输入客户姓名' };
  }

  if (!PHONE_PATTERN.test(phone)) {
    return { valid: false, field: 'phone', message: '请输入正确的客户手机号' };
  }

  if (!ID_CARD_PATTERN.test(idCard)) {
    return { valid: false, field: 'idCard', message: '请输入正确的身份证号' };
  }

  if (familyPhone && !PHONE_PATTERN.test(familyPhone)) {
    return { valid: false, field: 'familyPhone', message: '请输入正确的家属手机号' };
  }

  return {
    valid: true,
    value: {
      name,
      phone,
      idCard: idCard.toUpperCase(),
      medicalAccount: String(value.medicalAccount || '').trim(),
      familyPhone
    }
  };
}

function maskPhone(phone) {
  const value = compact(phone);

  if (value.length !== 11) {
    return value;
  }

  return `${value.slice(0, 3)}****${value.slice(-4)}`;
}

function maskIdCard(idCard) {
  const value = compact(idCard);

  if (value.length < 8) {
    return value;
  }

  return `${value.slice(0, 4)}********${value.slice(-4)}`;
}

function pad(value) {
  return String(value).padStart(2, '0');
}

function formatBindingTime(date = new Date()) {
  return [
    date.getFullYear(),
    '年',
    date.getMonth() + 1,
    '月',
    date.getDate(),
    '日 ',
    pad(date.getHours()),
    ':',
    pad(date.getMinutes())
  ].join('');
}

function adaptSelectablePromoters(payload = {}) {
  const items = Array.isArray(payload.items) ? payload.items : []
  return {
    items: items.map((item) => ({ id: String(item.promoterId || ''), name: String(item.displayName || '未命名推广人'), orgName: String(item.orgNodeName || ''), avatar: String(item.avatarUrl || ''), code: String(item.promoterCode || ''), bindingCount: Number.isSafeInteger(item.bindingCount) ? item.bindingCount : 0 })),
    nextCursor: payload.nextCursor ? String(payload.nextCursor) : '', hasMore: payload.hasMore === true
  }
}

module.exports = {
  validateCustomerForm,
  maskPhone,
  maskIdCard,
  formatBindingTime,
  adaptSelectablePromoters
};

const PHONE_PATTERN = /^1\d{10}$/;
const ID_CARD_PATTERN = /(^\d{15}$)|(^\d{17}[\dXx]$)/;

const EDITABLE_CUSTOMER_FIELDS = {
  name: {
    title: '修改姓名',
    type: 'text',
    maxlength: 20,
    required: true,
    sensitive: false
  },
  phone: {
    title: '修改手机号',
    type: 'number',
    maxlength: 11,
    required: true,
    sensitive: true
  },
  idCard: {
    title: '修改身份证号',
    type: 'idcard',
    maxlength: 18,
    required: false,
    sensitive: true
  },
  medicalAccount: {
    title: '修改医保账户',
    type: 'text',
    maxlength: 30,
    required: false,
    sensitive: true
  },
  familyPhone: {
    title: '修改家属手机号',
    type: 'number',
    maxlength: 11,
    required: false,
    sensitive: false
  }
};

function isMasked(value) {
  return String(value || '').includes('*');
}

function createCustomerEditForm(customer) {
  return {
    name: customer.name || '',
    phone: customer.phone || '',
    idCard: customer.idCard || '',
    medicalAccount: customer.medicalAccount || '',
    familyPhone: customer.familyPhone || '',
    note: customer.note || ''
  };
}

function validateEditField(field, input) {
  const config = EDITABLE_CUSTOMER_FIELDS[field];
  const value = String(input || '').trim();

  if (!config) {
    return { valid: false, message: '当前字段不可修改' };
  }

  if (config.required && !value) {
    return { valid: false, message: `请填写${config.title.slice(2)}` };
  }

  if (field === 'phone' && !isMasked(value) && !PHONE_PATTERN.test(value)) {
    return { valid: false, message: '请输入正确的手机号' };
  }

  if (field === 'familyPhone'
    && value
    && !isMasked(value)
    && !PHONE_PATTERN.test(value)) {
    return { valid: false, message: '请输入正确的家属手机号' };
  }

  if (field === 'idCard'
    && value
    && !isMasked(value)
    && !ID_CARD_PATTERN.test(value)) {
    return { valid: false, message: '请输入正确的身份证号' };
  }

  return { valid: true, value };
}

function validateCustomerEditForm(form) {
  for (const field of Object.keys(EDITABLE_CUSTOMER_FIELDS)) {
    const result = validateEditField(field, form[field]);

    if (!result.valid) {
      return { ...result, field };
    }
  }

  return {
    valid: true,
    value: {
      ...form,
      name: String(form.name || '').trim(),
      note: String(form.note || '').trim()
    }
  };
}

function adaptCustomerEditResponse(payload = {}) {
  return {
    id: String(payload.id || ''),
    name: String(payload.name || ''),
    phone: String(payload.phone || ''),
    note: String(payload.note || ''),
    familyPhone: String(payload.familyPhone || ''),
    version: Number.isSafeInteger(payload.version) ? payload.version : 0,
    reviewRequired: payload.reviewRequired === true
  }
}

module.exports = {
  EDITABLE_CUSTOMER_FIELDS,
  createCustomerEditForm,
  validateEditField,
  validateCustomerEditForm,
  adaptCustomerEditResponse
};

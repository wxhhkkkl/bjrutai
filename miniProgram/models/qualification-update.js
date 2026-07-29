const QUALIFICATION_TYPES = ['营业执照', '事业单位法人证书', '医疗机构执业许可证'];
const MAX_FILE_SIZE = 10 * 1024 * 1024;
const CREDIT_CODE_PATTERN = /^[0-9A-Z]{18}$/;
const ALLOWED_EXTENSIONS = ['pdf', 'jpg', 'jpeg', 'png'];

const DEFAULT_QUALIFICATION_FORM = {
  legalEntity: '北京鲁泰服务有限公司',
  qualificationType: '营业执照',
  creditCode: '91110108MA01ABCD2X',
  expiresAt: '2028-12-31'
};

const DEFAULT_QUALIFICATION_FILE = {
  name: '营业执照.pdf',
  size: 2.4 * 1024 * 1024,
  sizeLabel: '2.4 MB',
  extension: 'pdf',
  kind: 'pdf',
  path: '',
  existing: true
};

function createQualificationForm(source) {
  return Object.assign({}, DEFAULT_QUALIFICATION_FORM, source || {});
}

function formatFileSize(size) {
  const bytes = Number(size) || 0;

  if (bytes < 1024 * 1024) {
    return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  }

  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function getFileExtension(name) {
  const match = String(name || '').toLowerCase().match(/\.([a-z0-9]+)$/);
  return match ? match[1] : '';
}

function normalizeQualificationFile(file) {
  const value = file || {};
  const name = value.name || '营业执照.jpg';
  const extension = getFileExtension(name);
  const size = Number(value.size) || 0;

  return {
    name,
    size,
    sizeLabel: formatFileSize(size),
    extension,
    kind: extension === 'pdf' ? 'pdf' : 'image',
    path: value.path || value.tempFilePath || '',
    existing: value.existing === true
  };
}

function validateQualificationFile(file) {
  if (!file || !file.name) {
    return {
      valid: false,
      field: 'file',
      message: '请上传有效的资质文件'
    };
  }

  const extension = file.extension || getFileExtension(file.name);

  if (ALLOWED_EXTENSIONS.indexOf(extension) === -1) {
    return {
      valid: false,
      field: 'file',
      message: '仅支持 PDF、JPG、PNG 文件'
    };
  }

  if (Number(file.size) > MAX_FILE_SIZE) {
    return {
      valid: false,
      field: 'file',
      message: '文件大小不能超过 10 MB'
    };
  }

  return { valid: true };
}

function validateQualificationUpdate(form, file, confirmed, today) {
  const value = form || {};

  if (!String(value.legalEntity || '').trim()) {
    return {
      valid: false,
      field: 'legalEntity',
      message: '请输入法人主体'
    };
  }

  if (QUALIFICATION_TYPES.indexOf(value.qualificationType) === -1) {
    return {
      valid: false,
      field: 'qualificationType',
      message: '请选择资质类型'
    };
  }

  const creditCode = String(value.creditCode || '').trim().toUpperCase();

  if (!CREDIT_CODE_PATTERN.test(creditCode)) {
    return {
      valid: false,
      field: 'creditCode',
      message: '请输入正确的统一社会信用代码'
    };
  }

  if (!value.expiresAt) {
    return {
      valid: false,
      field: 'expiresAt',
      message: '请选择资质有效期'
    };
  }

  if (today && value.expiresAt <= today) {
    return {
      valid: false,
      field: 'expiresAt',
      message: '资质有效期必须晚于当前日期'
    };
  }

  const fileValidation = validateQualificationFile(file);
  if (!fileValidation.valid) return fileValidation;

  if (!confirmed) {
    return {
      valid: false,
      field: 'confirmation',
      message: '请确认资料真实、完整且有效'
    };
  }

  return {
    valid: true,
    value: {
      legalEntity: String(value.legalEntity).trim(),
      qualificationType: value.qualificationType,
      creditCode,
      expiresAt: value.expiresAt
    }
  };
}

module.exports = {
  QUALIFICATION_TYPES,
  MAX_FILE_SIZE,
  ALLOWED_EXTENSIONS,
  DEFAULT_QUALIFICATION_FORM,
  DEFAULT_QUALIFICATION_FILE,
  createQualificationForm,
  formatFileSize,
  getFileExtension,
  normalizeQualificationFile,
  validateQualificationFile,
  validateQualificationUpdate
};

const test = require('node:test');
const assert = require('node:assert/strict');
const {
  MAX_FILE_SIZE,
  DEFAULT_QUALIFICATION_FILE,
  createQualificationForm,
  normalizeQualificationFile,
  validateQualificationFile,
  validateQualificationUpdate
} = require('../../models/qualification-update');

test('qualification update starts from the approved information', () => {
  const form = createQualificationForm();

  assert.equal(form.legalEntity, '北京鲁泰服务有限公司');
  assert.equal(form.qualificationType, '营业执照');
  assert.equal(form.creditCode.length, 18);
});

test('qualification file accepts approved formats within ten megabytes', () => {
  const file = normalizeQualificationFile({
    name: '新营业执照.pdf',
    size: 2.4 * 1024 * 1024,
    path: 'wxfile://license.pdf'
  });

  assert.equal(file.kind, 'pdf');
  assert.equal(file.sizeLabel, '2.4 MB');
  assert.equal(validateQualificationFile(file).valid, true);
  assert.equal(
    validateQualificationFile({
      name: 'too-large.pdf',
      extension: 'pdf',
      size: MAX_FILE_SIZE + 1
    }).field,
    'file'
  );
});

test('qualification update validates identity date file and confirmation', () => {
  const form = createQualificationForm();

  assert.equal(
    validateQualificationUpdate(
      form,
      DEFAULT_QUALIFICATION_FILE,
      false,
      '2026-07-29'
    ).field,
    'confirmation'
  );
  assert.equal(
    validateQualificationUpdate(
      form,
      DEFAULT_QUALIFICATION_FILE,
      true,
      '2026-07-29'
    ).valid,
    true
  );
  assert.equal(
    validateQualificationUpdate(
      Object.assign({}, form, { expiresAt: '2026-07-01' }),
      DEFAULT_QUALIFICATION_FILE,
      true,
      '2026-07-29'
    ).field,
    'expiresAt'
  );
});

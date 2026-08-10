const test = require('node:test');
const assert = require('node:assert/strict');
const {
  DOCUMENT_VERSION,
  USER_AGREEMENT,
  PRIVACY_POLICY,
  getLegalDocument
} = require('../../models/legal-document');

test('legal documents provide complete, project-specific sections', () => {
  assert.equal(getLegalDocument('agreement'), USER_AGREEMENT);
  assert.equal(getLegalDocument('privacy'), PRIVACY_POLICY);
  assert.equal(getLegalDocument('unsupported'), null);
  assert.equal(USER_AGREEMENT.version, DOCUMENT_VERSION);
  assert.ok(USER_AGREEMENT.sections.length >= 6);
  assert.ok(PRIVACY_POLICY.sections.length >= 6);
  assert.match(PRIVACY_POLICY.sections.flatMap((item) => item.paragraphs).join(''), /腾讯云对象存储/);
});

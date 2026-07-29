const test = require('node:test');
const assert = require('node:assert/strict');
const {
  QUALIFICATION_STATES,
  normalizeQualificationState,
  getQualificationView
} = require('../../models/qualification-status');

test('qualification status exposes the four approved designs', () => {
  assert.deepEqual(
    Object.keys(QUALIFICATION_STATES),
    ['approved', 'reviewing', 'rejected', 'expiring']
  );
});

test('qualification status normalizes unsupported states to reviewing', () => {
  assert.equal(normalizeQualificationState('inactive'), 'reviewing');
  assert.equal(getQualificationView('unknown').id, 'reviewing');
});

test('qualification status adds the correct state-specific information', () => {
  const approved = getQualificationView('approved');
  const rejected = getQualificationView('rejected');
  const expiring = getQualificationView('expiring');

  assert.equal(approved.information[3].label, '有效期至');
  assert.match(rejected.reason, /营业执照有效期/);
  assert.equal(expiring.information[3].warning, true);
  assert.match(approved.banner, /qualification-approved-banner\.png$/);
});

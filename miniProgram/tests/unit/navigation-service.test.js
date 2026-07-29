const test = require('node:test');
const assert = require('node:assert/strict');
const {
  openAction
} = require('../../services/navigation-service');

test('qualification action follows the current account status', () => {
  const result = openAction('qualification', {
    role: 'promoter',
    qualificationStatus: 'expiring'
  });

  assert.equal(
    result.url,
    '/pages/qualification/status/index?state=expiring'
  );
});

test('qualification action falls back to reviewing for unknown states', () => {
  const result = openAction('qualification', {
    role: 'promoter',
    qualificationStatus: 'unknown'
  });

  assert.equal(
    result.url,
    '/pages/qualification/status/index?state=reviewing'
  );
});

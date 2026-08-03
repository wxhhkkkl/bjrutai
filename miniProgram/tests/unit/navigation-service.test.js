const test = require('node:test');
const assert = require('node:assert/strict');
const {
  openAction
} = require('../../services/navigation-service');

test('known action opens its configured path', () => {
  const result = openAction('promote-code', {
    role: 'promoter',
    activationStatus: 'active'
  });

  assert.equal(result.ok, true);
  assert.equal(result.url, '/pages/promotion-code/index');
});

test('unknown action is rejected', () => {
  const result = openAction('qualification', {
    role: 'promoter',
    activationStatus: 'active'
  });

  assert.equal(result.ok, false);
});

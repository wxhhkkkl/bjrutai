const test = require('node:test');
const assert = require('node:assert/strict');
const {
  CONTRIBUTION_RECORDS,
  normalizeCustomerDetailTab,
  getCustomerDetail,
  filterContributionRecords
} = require('../../models/customer-detail');

test('customer detail normalizes tab and customer selection', () => {
  assert.equal(normalizeCustomerDetailTab('contribution'), 'contribution');
  assert.equal(normalizeCustomerDetailTab('service'), 'contribution');
  assert.equal(normalizeCustomerDetailTab('unknown'), 'contribution');
  assert.equal(getCustomerDetail('customer-001').name, '王女士');
});

test('customer contribution filters return independent lists', () => {
  const bindings = filterContributionRecords(
    CONTRIBUTION_RECORDS,
    'binding'
  );
  const all = filterContributionRecords(CONTRIBUTION_RECORDS, 'all');

  assert.equal(bindings.length, 1);
  assert.equal(bindings[0].category, 'binding');
  assert.notEqual(all, CONTRIBUTION_RECORDS);
});

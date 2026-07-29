const test = require('node:test');
const assert = require('node:assert/strict');
const {
  CONTRIBUTION_RECORDS,
  getContributionMonth,
  getStatusFilters,
  filterContributionDetails,
  groupContributionDetails
} = require('../../models/contribution-detail');

test('contribution detail exposes approved July summary', () => {
  const month = getContributionMonth('2026-07');

  assert.equal(month.total, '12,680');
  assert.deepEqual(
    getStatusFilters(month).map((item) => item.count),
    [12, 10, 2]
  );
});

test('contribution detail combines month status and category filters', () => {
  const records = filterContributionDetails(CONTRIBUTION_RECORDS, {
    month: '2026-07',
    status: 'settled',
    category: 'binding'
  });

  assert.equal(records.length, 2);
  assert.ok(records.every((record) => record.status === 'settled'));
  assert.ok(records.every((record) => record.category === 'binding'));
});

test('contribution records group adjacent items by display date', () => {
  const july = filterContributionDetails(CONTRIBUTION_RECORDS, {
    month: '2026-07',
    status: 'all',
    category: 'all'
  });
  const groups = groupContributionDetails(july);

  assert.equal(groups.length, 4);
  assert.equal(groups[2].date, '7月14日');
  assert.equal(groups[2].items.length, 2);
});

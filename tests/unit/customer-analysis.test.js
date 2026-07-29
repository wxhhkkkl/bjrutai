const test = require('node:test');
const assert = require('node:assert/strict');
const {
  getCustomerAnalysisPeriod,
  getBindingDistribution
} = require('../../models/customer-analysis');

test('customer analysis falls back to the approved 30 day period', () => {
  assert.equal(getCustomerAnalysisPeriod('month').overview.total, 39);
  assert.equal(getCustomerAnalysisPeriod('unknown').id, 'month');
});

test('binding distribution is derived from period metrics', () => {
  const distribution = getBindingDistribution(
    getCustomerAnalysisPeriod('month')
  );

  assert.deepEqual(
    distribution.map((item) => item.value),
    [36, 3]
  );
  assert.equal(distribution[0].percent, 92);
  assert.equal(distribution[1].percent, 8);
});

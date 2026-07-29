const test = require('node:test');
const assert = require('node:assert/strict');
const {
  BINDING_RECORDS,
  filterBindingRecords,
  sortBindingRecords
} = require('../../models/binding-records');

test('binding records combine status and identity search', () => {
  assert.deepEqual(
    filterBindingRecords(BINDING_RECORDS, 'bound', '138').map(
      (record) => record.name
    ),
    ['王女士']
  );
  assert.deepEqual(
    filterBindingRecords(BINDING_RECORDS, 'matching', '刘'),
    []
  );
});

test('binding record sorting does not mutate source data', () => {
  const originalOrder = BINDING_RECORDS.map((record) => record.id);
  const sorted = sortBindingRecords(BINDING_RECORDS, 'status');

  assert.equal(sorted[0].status, 'processing');
  assert.deepEqual(
    BINDING_RECORDS.map((record) => record.id),
    originalOrder
  );
});

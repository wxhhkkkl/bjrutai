const test = require('node:test');
const assert = require('node:assert/strict');
const {
  normalizeResultState,
  getResultStateForRecord,
  getBindingResultViewModel
} = require('../../models/binding-result');

test('binding result normalizes unknown states', () => {
  assert.equal(normalizeResultState('bound'), 'bound');
  assert.equal(normalizeResultState('unexpected'), 'matching');
});

test('binding records map to the approved result states', () => {
  assert.equal(getResultStateForRecord({ status: 'bound' }), 'bound');
  assert.equal(getResultStateForRecord({ status: 'matching' }), 'matching');
  assert.equal(getResultStateForRecord({ status: 'processing' }), 'failed');
});

test('binding result view models reference sliced hero assets', () => {
  assert.equal(
    getBindingResultViewModel('failed').heroImage,
    '/assets/images/binding-result-failed.png'
  );
});

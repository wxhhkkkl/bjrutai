const test = require('node:test'); const assert = require('node:assert/strict'); const state = require('../../models/view-state')
test('view state normalizes invalid values', () => { assert.equal(state.normalizeViewState('empty'), 'empty'); assert.equal(state.normalizeViewState('bad'), 'success') })

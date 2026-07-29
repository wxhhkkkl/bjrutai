const test = require('node:test'); const assert = require('node:assert/strict'); const demo = require('../../mock/demo-control')
test('demo control stores valid states', () => { demo.resetDemoControl(); demo.setPageViewState('home', 'empty'); assert.equal(demo.getPageViewState('home'), 'empty'); demo.setPageViewState('home', 'bad'); assert.equal(demo.getPageViewState('home'), 'success') })

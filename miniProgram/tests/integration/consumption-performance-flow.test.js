const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs'); const path = require('node:path')
const root = path.resolve(__dirname, '../..')

test('consumption page uses real service and removes Demo fixtures', () => {
  const source = fs.readFileSync(path.join(root, 'pages/contribution/index.js'), 'utf8')
  assert.match(source, /consumption-service/); assert.doesNotMatch(source, /mock\/foundation-fixtures|mock\/demo-control/); assert.match(source, /requestVersion/)
})
test('consumption detail list does not open a single-bill detail', () => {
  const source = fs.readFileSync(path.join(root, 'pages/contribution-detail/index.js'), 'utf8')
  assert.doesNotMatch(source, /getBillDetail/)
  assert.doesNotMatch(source, /openContribution/)
})

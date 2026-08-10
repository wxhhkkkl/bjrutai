const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const root = path.resolve(__dirname, '../..')

test('binding pages use binding service and no fixture success path', () => {
  for (const file of ['pages/customer-binding/index.js', 'pages/binding-records/index.js']) {
    const source = fs.readFileSync(path.join(root, file), 'utf8')
    assert.match(source, /binding-service/)
    assert.doesNotMatch(source, /mock\/foundation-fixtures/)
  }
  const source = fs.readFileSync(path.join(root, 'pages/customer-binding/index.js'), 'utf8')
  assert.match(source, /Idempotency|idempotency|submitBinding/)
})

test('binding result does not request unverified detail or retry endpoints', () => {
  const source = fs.readFileSync(path.join(root, 'pages/binding-result/index.js'), 'utf8')
  assert.doesNotMatch(source, /getBindingDetail|retryBinding|binding-requests\//)
  assert.match(source, /暂不可用|管理员|blocked|受控/)
})

const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')

const root = path.resolve(__dirname, '../..')

test('customer production pages use customer service and no fixture imports', () => {
  for (const relative of [
    'pages/customers/index.js',
    'pages/customer-detail/index.js',
    'pages/customer-edit/index.js',
    'pages/customer-analysis/index.js'
  ]) {
    const source = fs.readFileSync(path.join(root, relative), 'utf8')
    assert.match(source, /customer-service/)
    assert.doesNotMatch(source, /mock\/foundation-fixtures|mock\/demo-control/)
  }
})

test('customer pages include request-version protection and API error states', () => {
  for (const relative of [
    'pages/customers/index.js',
    'pages/customer-detail/index.js',
    'pages/customer-analysis/index.js'
  ]) {
    const source = fs.readFileSync(path.join(root, relative), 'utf8')
    assert.match(source, /requestVersion/)
    assert.match(source, /FORBIDDEN|forbidden/)
    assert.match(source, /recoverable-error/)
  }
})

test('customer detail keeps blocked service/followup operations local and does not call endpoints', () => {
  const source = fs.readFileSync(path.join(root, 'pages/customer-detail/index.js'), 'utf8')
  assert.doesNotMatch(source, /getServiceRecords|getFollowups|postFollowup|\/service-records|\/followups/)
  assert.match(source, /暂不可用|权限|blocked|B-003|B-005/)
})

test('followup page keeps draft and submit actions blocked without fake success', () => {
  const source = fs.readFileSync(path.join(root, 'pages/followup-record/index.js'), 'utf8')
  assert.doesNotMatch(source, /mock\/foundation-fixtures|customer-service|request\(/)
  assert.match(source, /暂不能提交|blockedMessage/)
  assert.doesNotMatch(source, /草稿已保存|跟进已保存/)
})

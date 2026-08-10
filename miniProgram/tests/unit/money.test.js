const test = require('node:test')
const assert = require('node:assert/strict')

const { formatYuan } = require('../../utils/money')

test('formats integer cents without floating point arithmetic', () => {
  assert.equal(formatYuan(0), '¥0.00')
  assert.equal(formatYuan(1), '¥0.01')
  assert.equal(formatYuan(120000), '¥1,200.00')
  assert.equal(formatYuan(-305), '-¥3.05')
  assert.equal(formatYuan(9007199254740900), '¥90,071,992,547,409.00')
})

test('supports display without a currency symbol', () => {
  assert.equal(formatYuan(12345, { symbol: false }), '123.45')
})

test('rejects non-integer or unsafe cent values', () => {
  assert.throws(() => formatYuan(12.5), /整数分/)
  assert.throws(() => formatYuan('1200'), /整数分/)
  assert.throws(() => formatYuan(Number.MAX_SAFE_INTEGER + 1), /安全范围/)
})

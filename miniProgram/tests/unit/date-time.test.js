const test = require('node:test')
const assert = require('node:assert/strict')

const {
  formatChinaDateTime,
  formatMonthLabel
} = require('../../utils/date-time')

test('formats ISO timestamps in Asia Shanghai time', () => {
  assert.equal(
    formatChinaDateTime('2026-08-08T01:05:00Z'),
    '2026年8月8日 09:05'
  )
  assert.equal(
    formatChinaDateTime('2026-08-08T10:30:00+08:00'),
    '2026年8月8日 10:30'
  )
})

test('returns an empty display for absent or invalid timestamps', () => {
  assert.equal(formatChinaDateTime(null), '')
  assert.equal(formatChinaDateTime('not-a-date'), '')
})

test('formats a validated API month without Date timezone conversion', () => {
  assert.equal(formatMonthLabel('2026-08'), '2026年8月')
  assert.equal(formatMonthLabel('2026-13'), '')
  assert.equal(formatMonthLabel('August'), '')
})

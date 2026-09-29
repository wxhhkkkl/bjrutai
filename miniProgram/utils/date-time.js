const CHINA_OFFSET_MS = 8 * 60 * 60 * 1000

function pad(value) {
  return String(value).padStart(2, '0')
}

function formatChinaDateTime(value) {
  if (!value) return ''

  const input = typeof value === 'string' ? value.trim() : value
  const hasTimezone = typeof input === 'string' && /(?:z|[+-]\d{2}:?\d{2})$/i.test(input)
  const hasTime = typeof input === 'string' && /T\d{2}:\d{2}/.test(input)
  // Backend DateTime columns are stored as UTC; MySQL responses may omit the
  // timezone suffix, so interpret an offset-less ISO datetime as UTC.
  const normalized = hasTime && !hasTimezone ? `${input}Z` : input
  const timestamp = new Date(normalized).getTime()
  if (!Number.isFinite(timestamp)) return ''

  const china = new Date(timestamp + CHINA_OFFSET_MS)
  return [
    china.getUTCFullYear(),
    '年',
    china.getUTCMonth() + 1,
    '月',
    china.getUTCDate(),
    '日 ',
    pad(china.getUTCHours()),
    ':',
    pad(china.getUTCMinutes())
  ].join('')
}

function formatMonthLabel(value) {
  const match = /^(\d{4})-(\d{2})$/.exec(String(value || ''))
  if (!match) return ''

  const month = Number(match[2])
  if (month < 1 || month > 12) return ''

  return `${match[1]}年${month}月`
}

module.exports = {
  formatChinaDateTime,
  formatMonthLabel
}

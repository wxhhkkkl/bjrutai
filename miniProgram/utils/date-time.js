const CHINA_OFFSET_MS = 8 * 60 * 60 * 1000

function pad(value) {
  return String(value).padStart(2, '0')
}

function chinaDate(value) {
  if (!value) return ''

  const input = typeof value === 'string' ? value.trim() : value
  const hasTimezone = typeof input === 'string' && /(?:z|[+-]\d{2}:?\d{2})$/i.test(input)
  const hasTime = typeof input === 'string' && /T\d{2}:\d{2}/.test(input)
  // Backend DateTime columns are stored as UTC; MySQL responses may omit the
  // timezone suffix, so interpret an offset-less ISO datetime as UTC.
  let normalized = hasTime && !hasTimezone ? `${input}Z` : input
  if (typeof normalized === 'string') {
    // JavaScript engines may reject SQL timestamps with microsecond precision.
    normalized = normalized.replace(/(\.\d{3})\d+(?=(?:z|[+-]\d{2}:?\d{2})?$)/i, '$1')
  }
  const timestamp = new Date(normalized).getTime()
  if (!Number.isFinite(timestamp)) return ''

  return new Date(timestamp + CHINA_OFFSET_MS)
}

function formatChinaDateTime(value, options = {}) {
  const china = chinaDate(value)
  if (!china) return ''
  const formatted = [
    china.getUTCFullYear(),
    '年',
    china.getUTCMonth() + 1,
    '月',
    china.getUTCDate(),
    '日 ',
    pad(china.getUTCHours()),
    ':',
    pad(china.getUTCMinutes())
  ]
  if (options.includeSeconds) formatted.push(':', pad(china.getUTCSeconds()))
  return formatted.join('')
}

function formatChinaDateTimeCompact(value) {
  const china = chinaDate(value)
  if (!china) return ''
  return `${china.getUTCFullYear()}-${pad(china.getUTCMonth() + 1)}-${pad(china.getUTCDate())} ${pad(china.getUTCHours())}:${pad(china.getUTCMinutes())}`
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
  formatChinaDateTimeCompact,
  formatMonthLabel
}

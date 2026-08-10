const CHINA_OFFSET_MS = 8 * 60 * 60 * 1000

function pad(value) {
  return String(value).padStart(2, '0')
}

function formatChinaDateTime(value) {
  if (!value) return ''

  const timestamp = new Date(value).getTime()
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

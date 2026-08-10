function groupThousands(value) {
  return String(value).replace(/\B(?=(\d{3})+(?!\d))/g, ',')
}

function formatYuan(cents, options = {}) {
  if (typeof cents !== 'number' || !Number.isInteger(cents)) {
    throw new TypeError('金额必须使用整数分')
  }
  if (!Number.isSafeInteger(cents)) {
    throw new RangeError('金额超出安全范围')
  }

  const negative = cents < 0
  const absolute = Math.abs(cents)
  const yuan = Math.floor(absolute / 100)
  const fen = String(absolute % 100).padStart(2, '0')
  const amount = `${groupThousands(yuan)}.${fen}`
  const symbol = options.symbol === false ? '' : '¥'

  return `${negative ? '-' : ''}${symbol}${amount}`
}

module.exports = {
  formatYuan
}

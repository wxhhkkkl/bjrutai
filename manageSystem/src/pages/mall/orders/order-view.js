export const orderStates = {
  pending_payment: '待付款',
  pending_shipment: '待发货',
  pending_receipt: '待收货',
  completed: '已完成',
  closed: '已关闭',
}
export const paymentStates = {
  not_started: '未发起付款',
  creating: '准备中',
  pending: '待付款',
  unknown: '收款确认中',
  succeeded: '已核实收款',
  closed: '已关闭',
  failed: '需核实',
}
export function money(value) {
  if (!Number.isSafeInteger(value)) return '—'
  const amount = BigInt(value)
  const absolute = amount < 0n ? -amount : amount
  return `${amount < 0n ? '-' : ''}${absolute / 100n}.${String(absolute % 100n).padStart(2, '0')}`
}
export function time(value) {
  if (!value || Number.isNaN(new Date(value).getTime())) return '—'
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(new Date(value))
}

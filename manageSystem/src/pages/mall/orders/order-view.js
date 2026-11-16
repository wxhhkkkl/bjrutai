export const orderStates = {
  pending_payment: '待付款',
  pending_shipment: '待履约',
  pending_receipt: '待收货',
  completed: '已完成',
  closed: '已关闭',
}
export function orderStatusLabel(order) {
  if (order && order.status === 'pending_shipment' && order.deliveryMethod === 'virtual') {
    return '待交付'
  }
  if (order && order.status === 'pending_shipment') return '待发货'
  return orderStates[order && order.status] || '待核实'
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
export function orderStatusType(status) {
  return (
    {
      pending_payment: 'warning',
      pending_shipment: 'danger',
      pending_receipt: 'primary',
      completed: 'success',
      closed: 'info',
    }[status] || 'info'
  )
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

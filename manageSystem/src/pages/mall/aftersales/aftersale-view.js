import { money, time } from '../orders/order-view'

export const aftersaleStates = {
  submitted: '待审核',
  awaiting_return: '待买家寄回',
  awaiting_receipt: '待验收退货',
  awaiting_refund: '待发起退款',
  refunding: '退款核实中',
  disputed: '待人工核实',
  completed: '已完成',
  rejected: '已拒绝',
  withdrawn: '已撤回',
}

export const aftersaleMethods = {
  refund_only: '仅退款',
  return_refund: '退货退款',
}

export function aftersaleStateType(status) {
  if (status === 'completed') return 'success'
  if (['submitted', 'awaiting_refund', 'refunding'].includes(status)) return 'warning'
  if (status === 'disputed') return 'danger'
  if (status === 'awaiting_return' || status === 'awaiting_receipt') return 'primary'
  return 'info'
}

export { money, time }

import { afterEach, expect, it, vi } from 'vitest'
import http from '@/api/http'
import {
  decideAftersale,
  executeAftersaleRefund,
  getAdminAftersale,
  getAdminMallRefund,
  getAftersaleProofAccess,
  listAdminAftersales,
  queryAdminMallRefund,
  receiveAftersaleReturn,
  retryAdminMallRefund,
} from '@/api/mall-aftersales'

vi.mock('@/api/http', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}))
afterEach(() => vi.clearAllMocks())

it('sends only applied status filters to the permissioned aftersale list', async () => {
  http.get.mockResolvedValue({ data: { data: { items: [], total: 0 } } })
  const params = {
    status: 'awaiting_receipt',
    cursor: 'opaque-cursor',
    pageSize: 20,
  }
  await listAdminAftersales(params)
  expect(http.get).toHaveBeenCalledWith('/admin/mall/aftersales', { params })
  http.get.mockResolvedValue({ data: { data: { id: '8' } } })
  expect((await getAdminAftersale('8')).id).toBe('8')
  expect(http.get).toHaveBeenLastCalledWith('/admin/mall/aftersales/8')
  http.get.mockResolvedValue({
    data: { data: { id: '15', status: 'unknown' } },
  })
  expect((await getAdminMallRefund('15')).status).toBe('unknown')
  expect(http.get).toHaveBeenLastCalledWith('/admin/mall/refunds/15')
})

it('keeps review, receipt and refund execution as separate keyed operations', async () => {
  http.post.mockResolvedValue({ data: { data: { status: 'prepared' } } })
  await decideAftersale(
    {
      id: '8',
      expectedVersion: 3,
      decision: 'approve',
      reason: '满足退货条件',
    },
    'aftersale-review-key'
  )
  expect(http.post).toHaveBeenNthCalledWith(
    1,
    '/admin/mall/aftersales/8/decision',
    { expectedVersion: 3, decision: 'approve', reason: '满足退货条件' },
    { headers: { 'Idempotency-Key': 'aftersale-review-key' } }
  )
  await receiveAftersaleReturn(
    {
      id: '8',
      expectedVersion: 4,
      result: 'partially_accepted',
      sellableItems: [{ aftersaleItemId: '80', quantity: 1 }],
      reason: '一件可售，一件损坏',
    },
    'aftersale-receipt-key'
  )
  await executeAftersaleRefund(
    { id: '8', expectedVersion: 5 },
    'aftersale-refund-key'
  )
  expect(http.post).toHaveBeenNthCalledWith(
    2,
    '/admin/mall/aftersales/8/receipt',
    {
      expectedVersion: 4,
      result: 'partially_accepted',
      sellableItems: [{ aftersaleItemId: '80', quantity: 1 }],
      reason: '一件可售，一件损坏',
    },
    { headers: { 'Idempotency-Key': 'aftersale-receipt-key' } }
  )
  expect(http.post).toHaveBeenNthCalledWith(
    3,
    '/admin/mall/aftersales/8/execute-refund',
    { expectedVersion: 5 },
    { headers: { 'Idempotency-Key': 'aftersale-refund-key' } }
  )
  await queryAdminMallRefund(
    { id: '15', expectedVersion: 4 },
    'refund-query-key'
  )
  await retryAdminMallRefund(
    { id: '15', expectedVersion: 4, reason: '请求结果未知' },
    'refund-retry-key'
  )
  expect(http.post).toHaveBeenNthCalledWith(
    4,
    '/admin/mall/refunds/15/query',
    { expectedVersion: 4 },
    { headers: { 'Idempotency-Key': 'refund-query-key' } }
  )
  expect(http.post).toHaveBeenNthCalledWith(
    5,
    '/admin/mall/refunds/15/retry',
    { expectedVersion: 4, reason: '请求结果未知' },
    { headers: { 'Idempotency-Key': 'refund-retry-key' } }
  )
})

it('uses a short-lived private access endpoint for submitted proof only', async () => {
  http.get.mockResolvedValue({
    data: {
      data: { fileId: '12', accessUrl: 'https://storage.invalid/short' },
    },
  })
  expect((await getAftersaleProofAccess('12')).accessUrl).toMatch(/^https:/)
  expect(http.get).toHaveBeenCalledWith('/admin/mall/files/12/access')
})

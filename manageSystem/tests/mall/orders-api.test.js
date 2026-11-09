import { afterEach, expect, it, vi } from 'vitest'
import http from '@/api/http'
import {
  saveNote,
  cancelOrder,
  correctTracking,
  getCommand,
  listOrders,
  registerShipment,
} from '@/api/mall-orders'
import { money, time } from '@/pages/mall/orders/order-view'

vi.mock('@/api/http', () => ({
  default: { get: vi.fn(), patch: vi.fn(), post: vi.fn() },
}))
afterEach(() => vi.clearAllMocks())
it('preserves version and caller intent key without putting IDs into write bodies', async () => {
  http.patch.mockResolvedValue({ data: { data: { id: '9', version: 4 } } })
  http.post.mockResolvedValue({
    data: { data: { commandId: '7', status: 'pending' } },
  })
  await saveNote(
    { id: '9', expectedVersion: 3, internalNote: '库房核实' },
    'order-note-test-key'
  )
  expect(http.patch).toHaveBeenCalledWith(
    '/admin/mall/orders/9/note',
    { expectedVersion: 3, internalNote: '库房核实' },
    { headers: { 'Idempotency-Key': 'order-note-test-key' } }
  )
  expect(
    (
      await cancelOrder(
        { id: '9', expectedVersion: 3, reason: '取消' },
        'order-cancel-test-key'
      )
    ).status
  ).toBe('pending')
  expect(http.post.mock.calls[0][0]).toBe('/admin/mall/orders/9/cancel')
  http.get.mockResolvedValue({ data: { data: { status: 'manual' } } })
  expect((await getCommand('7')).status).toBe('manual')
  expect(http.get).toHaveBeenLastCalledWith('/admin/mall/commands/7')
})
it('sends only applied filters and formats cents without losing large integer precision', async () => {
  http.get.mockResolvedValue({ data: { data: { items: [] } } })
  const filters = {
    status: 'closed',
    orderNo: 'M-9',
    cursor: 'cursor',
    from: '2026-11-01T00:00:00Z',
  }
  await listOrders(filters)
  expect(http.get).toHaveBeenCalledWith('/admin/mall/orders', {
    params: filters,
  })
  expect(money(9007199254740991)).toBe('90071992547409.91')
  expect(money(1)).toBe('0.01')
  expect(money(null)).toBe('—')
  expect(time('2026-11-05T16:01:02Z')).toContain('2026/11/06')
})

it('routes local dispatch and tracking correction with their stable command keys', async () => {
  http.post.mockResolvedValue({ data: { data: { id: '30', version: 1 } } })
  http.patch.mockResolvedValue({ data: { data: { id: '30', version: 2 } } })
  const ship = await registerShipment(
    { id: '9', expectedVersion: 3, courierCode: 'yuantong', trackingNo: 'YT2026' },
    'ship-local-command-key'
  )
  const correction = await correctTracking(
    {
      shipmentId: '30',
      expectedVersion: 4,
      shipmentVersion: 1,
      courierCode: 'shunfeng',
      trackingNo: 'SF2026',
      reason: '录入错误',
    },
    'tracking-correction-key'
  )
  expect(ship.id).toBe('30')
  expect(correction.version).toBe(2)
  expect(http.post).toHaveBeenCalledWith(
    '/admin/mall/orders/9/ship',
    { expectedVersion: 3, courierCode: 'yuantong', trackingNo: 'YT2026' },
    { headers: { 'Idempotency-Key': 'ship-local-command-key' } }
  )
  expect(http.patch).toHaveBeenCalledWith(
    '/admin/mall/shipments/30',
    {
      expectedVersion: 4,
      shipmentVersion: 1,
      courierCode: 'shunfeng',
      trackingNo: 'SF2026',
      reason: '录入错误',
    },
    { headers: { 'Idempotency-Key': 'tracking-correction-key' } }
  )
})

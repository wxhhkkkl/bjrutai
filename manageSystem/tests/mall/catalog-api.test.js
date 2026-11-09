import { afterEach, expect, it, vi } from 'vitest'
import { webcrypto } from 'node:crypto'
import { Buffer } from 'node:buffer'
import http from '@/api/http'
import { saveProduct, uploadProductImage } from '@/api/mall-catalog'

vi.mock('@/api/http', () => ({ default: { post: vi.fn(), patch: vi.fn() } }))
afterEach(() => {
  vi.clearAllMocks()
  vi.unstubAllGlobals()
})
it('sends versioned writes with the provided idempotency key', async () => {
  http.patch.mockResolvedValue({ data: { data: { id: '8' } } })
  await saveProduct(
    { id: '8', expectedVersion: 4, product: { name: '商品' } },
    'mall-command-test-001'
  )
  expect(http.patch).toHaveBeenCalledWith(
    '/admin/mall/products/8',
    {
      expectedVersion: 4,
      product: { name: '商品' },
    },
    { headers: { 'Idempotency-Key': 'mall-command-test-001' } }
  )
})
it('retries lost verification without uploading again and never sends admin auth to COS', async () => {
  vi.stubGlobal('crypto', webcrypto)
  const fetcher = vi.fn().mockResolvedValue({ ok: true })
  vi.stubGlobal('fetch', fetcher)
  http.post
    .mockResolvedValueOnce({
      data: {
        data: { fileId: '3', uploadUrl: 'https://storage.invalid/staging' },
      },
    })
    .mockRejectedValueOnce(new Error('lost verify response'))
    .mockResolvedValueOnce({ data: { data: { id: '3', status: 'verified' } } })
  const state = {
    file: {
      name: 'a.jpg',
      type: 'image/jpeg',
      size: 3,
      arrayBuffer: async () => Buffer.from([1, 2, 3]),
    },
    ticketKey: 'ticket-command-001',
    verifyKey: 'verify-command-001',
  }
  await expect(uploadProductImage(state)).rejects.toThrow(
    'lost verify response'
  )
  expect(await uploadProductImage(state)).toMatchObject({ id: '3' })
  expect(fetcher).toHaveBeenCalledTimes(1)
  expect(fetcher.mock.calls[0][1]).toMatchObject({
    credentials: 'omit',
    redirect: 'error',
    headers: { 'Content-Type': 'image/jpeg' },
  })
  expect(fetcher.mock.calls[0][1].headers).not.toHaveProperty('Authorization')
  expect(http.post.mock.calls[2]).toEqual(http.post.mock.calls[1])
})

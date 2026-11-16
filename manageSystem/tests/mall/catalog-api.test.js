import { afterEach, expect, it, vi } from 'vitest'
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
it('uploads an image in one multipart request and caches the verified result', async () => {
  http.post.mockResolvedValue({ data: { data: { id: '3', status: 'verified' } } })
  const state = {
    file: new File([new Uint8Array([1, 2, 3])], 'a.jpg', {
      type: 'image/jpeg',
    }),
  }
  const result = await uploadProductImage(state)
  expect(result).toEqual({ id: '3', status: 'verified' })
  expect(http.post).toHaveBeenCalledWith(
    '/admin/mall/products/images',
    expect.any(FormData),
    { headers: { 'Content-Type': undefined } }
  )
  expect(await uploadProductImage(state)).toEqual(result)
  expect(http.post).toHaveBeenCalledTimes(1)
})

it('rejects a wrong-type or oversize image before making any request', async () => {
  await expect(
    uploadProductImage({
      file: new File(['x'], 'a.txt', { type: 'text/plain' }),
    })
  ).rejects.toThrow('JPG 或 PNG')
  await expect(
    uploadProductImage({
      file: new File([new Uint8Array(6 * 1024 * 1024)], 'a.jpg', {
        type: 'image/jpeg',
      }),
    })
  ).rejects.toThrow('5 MB')
  expect(http.post).not.toHaveBeenCalled()
})

import { beforeEach, describe, expect, it, vi } from 'vitest'

import http from '../http'
import { getComment, listComments, updateComment } from '../comments'

vi.mock('../http', () => ({
  default: { get: vi.fn(), patch: vi.fn() },
}))

describe('admin comments API', () => {
  beforeEach(() => vi.clearAllMocks())

  it('loads filtered comment pages with a cursor', async () => {
    http.get.mockResolvedValue({ data: { data: { items: [], nextCursor: null, hasMore: false, total: 0 } } })
    const params = { articleId: 3, status: 'pending', keyword: '友善', cursor: 'abc', limit: 20 }

    await expect(listComments(params)).resolves.toEqual({ items: [], nextCursor: null, hasMore: false, total: 0 })
    expect(http.get).toHaveBeenCalledWith('/admin/comments', { params })
  })

  it('sends an expectedVersion with every state-changing action', async () => {
    http.patch.mockResolvedValue({ data: { data: { commentId: '9', status: 'hidden', version: 4 } } })

    await updateComment('9', { action: 'hide', expectedVersion: 3, reason: '不适宜展示' })

    expect(http.patch).toHaveBeenCalledWith('/admin/comments/9', {
      action: 'hide', expectedVersion: 3, reason: '不适宜展示',
    })
  })

  it('loads the comment detail for the review drawer', async () => {
    http.get.mockResolvedValue({ data: { data: { commentId: '9', actions: [] } } })

    await getComment('9')

    expect(http.get).toHaveBeenCalledWith('/admin/comments/9')
  })
})

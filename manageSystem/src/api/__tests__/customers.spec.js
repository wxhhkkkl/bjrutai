import { beforeEach, describe, expect, it, vi } from 'vitest'

import http from '../http'
import { adminCustomerApi } from '../customers'

vi.mock('../http', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
  },
}))

describe('adminCustomerApi', () => {
  beforeEach(() => vi.clearAllMocks())

  it('exports the selected organization and creation date range as a blob', async () => {
    const response = { data: new Blob(['customers']) }
    http.get.mockResolvedValue(response)

    const result = await adminCustomerApi.export('12', {
      startDate: '2026-09-01',
      endDate: '2026-09-03',
      status: 'bound',
    })

    expect(http.get).toHaveBeenCalledWith('/admin/customers/export', {
      params: {
        orgId: '12',
        startDate: '2026-09-01',
        endDate: '2026-09-03',
        status: 'bound',
      },
      responseType: 'blob',
    })
    expect(result).toBe(response)
  })
})

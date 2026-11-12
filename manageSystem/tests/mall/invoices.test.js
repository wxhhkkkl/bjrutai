import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import InvoiceQueue from '@/pages/mall/invoices/index.vue'
import InvoiceDetail from '@/pages/mall/invoices/detail.vue'
import { useAuthStore } from '@/stores/auth'
import * as api from '@/api/mall-invoices'

const httpMocks = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
}))

vi.mock('@/api/http', () => ({ default: httpMocks }))

vi.mock('@/api/mall-invoices', () => ({
  listAdminMallInvoiceRequests: vi.fn(),
  getAdminMallInvoiceRequest: vi.fn(),
  claimMallInvoice: vi.fn(),
  needMallInvoiceInfo: vi.fn(),
  recordMallInvoice: vi.fn(),
  markMallRedPending: vi.fn(),
  recordMallRedInvoice: vi.fn(),
  replaceMallInvoiceFile: vi.fn(),
  createInvoicePdfUploadState: vi.fn(),
  uploadInvoicePdf: vi.fn(),
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
  onBeforeRouteLeave: vi.fn(),
  onBeforeRouteUpdate: vi.fn(),
}))

const blueInvoice = {
  id: '51',
  orderId: '9',
  requestId: '8',
  sellerIdentity: '北京鲁泰测试销售主体',
  invoiceNo: 'INV-TEST-51',
  kind: 'blue',
  totalCent: 10000,
  issuedAt: '2026-11-07T09:00:00Z',
  status: 'valid',
  originalInvoiceId: null,
  replacementForId: null,
  fileId: '120',
  version: 1,
}

const invoiceRequest = {
  id: '8',
  requestNo: 'IR-TEST-8',
  orderId: '9',
  buyerType: 'company',
  invoiceType: 'digital_normal',
  title: '鲁泰测试有限公司',
  taxNoMasked: '91**************26',
  status: 'submitted',
  requestedGoodsCent: 9900,
  requestedFreightCent: 100,
  netPaidCent: 10000,
  claimedBy: null,
  invoiceIds: [],
  invoices: [],
  version: 1,
}

function page(Component, permissions = ['mall.invoices.read']) {
  const pinia = createPinia()
  const auth = useAuthStore(pinia)
  auth.permissions = permissions
  auth.user = { userId: '31', account: 'finance-tester' }
  return mount(Component, {
    props: Component === InvoiceDetail ? { id: '8' } : {},
    global: { plugins: [pinia, ElementPlus] },
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  api.listAdminMallInvoiceRequests.mockResolvedValue({
    items: [structuredClone(invoiceRequest)],
    total: 1,
    nextCursor: null,
  })
  api.getAdminMallInvoiceRequest.mockResolvedValue(
    structuredClone(invoiceRequest)
  )
  api.createInvoicePdfUploadState.mockImplementation((file, orderId) => ({
    file,
    orderId,
  }))
  api.uploadInvoicePdf.mockResolvedValue({ id: '120', status: 'verified' })
})

afterEach(() => {
  vi.unstubAllGlobals()
})

it('shows only masked buyer tax data and never offers raw billing release', async () => {
  const wrapper = page(InvoiceQueue, ['mall.invoices.read'])
  await flushPromises()
  expect(wrapper.text()).toContain('IR-TEST-8')
  expect(wrapper.text()).toContain('91**************26')
  expect(wrapper.text()).not.toContain('91110000PRIVATE2026')
  expect(wrapper.find('[data-test="release-billing"]').exists()).toBe(false)
  expect(wrapper.find('[data-test="claim-invoice"]').exists()).toBe(false)
  wrapper.unmount()
})

it('shows special-invoice intent as a manual request for finance review', async () => {
  api.getAdminMallInvoiceRequest.mockResolvedValueOnce({
    ...structuredClone(invoiceRequest),
    invoiceType: 'manual_special_request',
  })
  const wrapper = page(InvoiceDetail, ['mall.invoices.read'])
  await flushPromises()
  expect(wrapper.text()).toContain('专票需求（人工核实）')
  wrapper.unmount()
})

it('filters server pages by invoice request status', async () => {
  const wrapper = page(InvoiceQueue, ['mall.invoices.read'])
  await flushPromises()
  wrapper.vm.statusFilter = 'needs_info'
  await wrapper.vm.searchLocal()
  expect(api.listAdminMallInvoiceRequests.mock.calls.at(-1)[0]).toEqual({
    pageSize: 20,
    status: 'needs_info',
  })
  wrapper.unmount()
})

it('requires a finance claim before uploading and recording a blue invoice', async () => {
  const claimed = {
    ...structuredClone(invoiceRequest),
    status: 'issuing',
    claimedBy: '31',
    version: 2,
  }
  api.claimMallInvoice.mockResolvedValue(claimed)
  api.getAdminMallInvoiceRequest
    .mockResolvedValueOnce(structuredClone(invoiceRequest))
    .mockResolvedValueOnce(structuredClone(claimed))
  api.recordMallInvoice.mockResolvedValue(blueInvoice)

  const wrapper = page(InvoiceDetail, [
    'mall.invoices.read',
    'mall.invoices.write',
  ])
  await flushPromises()
  expect(wrapper.find('[data-test="record-blue"]').exists()).toBe(false)
  expect(wrapper.find('[data-test="claim-invoice"]').exists()).toBe(true)

  await wrapper.vm.claim()
  expect(api.claimMallInvoice).toHaveBeenCalledWith(
    { id: '8', expectedVersion: 1 },
    expect.any(String)
  )

  const pdf = new File(['verified invoice bytes'], 'invoice.pdf', {
    type: 'application/pdf',
  })
  await wrapper.vm.uploadBlueFile(pdf)
  expect(api.uploadInvoicePdf).toHaveBeenCalledWith({ file: pdf, orderId: '9' })
  wrapper.vm.issueForm.invoiceNo = 'INV-TEST-51'
  wrapper.vm.issueForm.issuedAt = '2026-11-07T09:00:00Z'
  wrapper.vm.issueForm.sellerIdentity = '北京鲁泰测试销售主体'
  await wrapper.vm.recordBlue()

  expect(api.recordMallInvoice).toHaveBeenCalledWith(
    {
      id: '8',
      expectedVersion: 2,
      invoiceNo: 'INV-TEST-51',
      issuedAt: '2026-11-07T09:00:00.000Z',
      sellerIdentity: '北京鲁泰测试销售主体',
      totalCent: 10000,
      fileId: '120',
    },
    expect.any(String)
  )
  wrapper.unmount()
})

it('asks the buyer to correct invoice data through the versioned needs-info action', async () => {
  api.getAdminMallInvoiceRequest.mockResolvedValueOnce({
    ...structuredClone(invoiceRequest),
    status: 'issuing',
    claimedBy: '31',
  })
  api.needMallInvoiceInfo.mockResolvedValue({
    ...structuredClone(invoiceRequest),
    status: 'needs_info',
    version: 3,
  })
  const wrapper = page(InvoiceDetail, [
    'mall.invoices.read',
    'mall.invoices.write',
  ])
  await flushPromises()
  wrapper.vm.infoReason = '请买家确认企业抬头信息'
  await wrapper.vm.requestInfo()
  expect(api.needMallInvoiceInfo).toHaveBeenCalledWith(
    {
      id: '8',
      expectedVersion: 1,
      reason: '请买家确认企业抬头信息',
    },
    expect.any(String)
  )
  expect(wrapper.text()).not.toContain('91110000PRIVATE2026')
  wrapper.unmount()
})

it('replays the same invoice record intent after an uncertain response', async () => {
  api.getAdminMallInvoiceRequest.mockResolvedValueOnce({
    ...structuredClone(invoiceRequest),
    status: 'issuing',
    claimedBy: '31',
    version: 2,
  })
  api.uploadInvoicePdf.mockResolvedValue({ id: '120', status: 'verified' })
  api.recordMallInvoice
    .mockRejectedValueOnce(new Error('连接超时'))
    .mockResolvedValueOnce(blueInvoice)
  const wrapper = page(InvoiceDetail, [
    'mall.invoices.read',
    'mall.invoices.write',
  ])
  await flushPromises()
  await wrapper.vm.uploadBlueFile(
    new File(['invoice'], 'invoice.pdf', { type: 'application/pdf' })
  )
  Object.assign(wrapper.vm.issueForm, {
    invoiceNo: 'INV-TEST-51',
    issuedAt: '2026-11-07T09:00:00Z',
    sellerIdentity: '北京鲁泰测试销售主体',
  })
  await wrapper.vm.recordBlue()
  expect(wrapper.text()).toContain('结果未确认')
  const firstIntent = api.recordMallInvoice.mock.calls[0]
  await wrapper.vm.retry()
  expect(api.recordMallInvoice.mock.calls[1]).toEqual(firstIntent)
  wrapper.unmount()
})

it('keeps red invoice actions attached to the original blue invoice chain', async () => {
  const original = {
    ...structuredClone(blueInvoice),
    status: 'red_pending',
    version: 4,
  }
  api.getAdminMallInvoiceRequest.mockResolvedValueOnce({
    ...structuredClone(invoiceRequest),
    status: 'delivered',
    claimedBy: '31',
    invoices: [original],
    invoiceIds: [original.id],
    version: 3,
  })
  api.recordMallRedInvoice.mockResolvedValue({
    ...original,
    id: '52',
    kind: 'red',
    invoiceNo: 'INV-RED-52',
    totalCent: 10000,
    originalInvoiceId: original.id,
    status: 'valid',
  })
  const wrapper = page(InvoiceDetail, [
    'mall.invoices.read',
    'mall.invoices.write',
  ])
  await flushPromises()
  expect(wrapper.find('[data-test="record-red-51"]').exists()).toBe(true)
  expect(wrapper.text()).toContain('INV-TEST-51')
  wrapper.vm.redForms['51'].invoiceNo = 'INV-RED-52'
  wrapper.vm.redForms['51'].issuedAt = '2026-11-07T10:00:00Z'
  wrapper.vm.redForms['51'].totalCent = 10000
  wrapper.vm.redForms['51'].reason = '按退款事实办理红冲'
  await wrapper.vm.uploadRedFile(
    '51',
    new File(['red invoice'], 'red-invoice.pdf', { type: 'application/pdf' })
  )
  await wrapper.vm.recordRed('51')
  expect(api.recordMallRedInvoice).toHaveBeenCalledWith(
    {
      id: '51',
      expectedVersion: 4,
      invoiceNo: 'INV-RED-52',
      issuedAt: '2026-11-07T10:00:00.000Z',
      totalCent: 10000,
      fileId: '120',
      reason: '按退款事实办理红冲',
    },
    expect.any(String)
  )
  wrapper.unmount()
})

it('reissues only after the old blue invoice is fully red and uses current net paid amount', async () => {
  const oldBlue = {
    ...structuredClone(blueInvoice),
    status: 'fully_red',
    version: 5,
  }
  const oldRed = {
    ...structuredClone(blueInvoice),
    id: '52',
    invoiceNo: 'INV-RED-52',
    kind: 'red',
    totalCent: 5000,
    originalInvoiceId: oldBlue.id,
    status: 'valid',
  }
  api.getAdminMallInvoiceRequest.mockResolvedValueOnce({
    ...structuredClone(invoiceRequest),
    status: 'delivered',
    claimedBy: '31',
    netPaidCent: 5000,
    invoices: [oldBlue, oldRed],
    invoiceIds: [oldBlue.id, oldRed.id],
    version: 3,
  })
  api.recordMallInvoice.mockResolvedValue({
    ...structuredClone(blueInvoice),
    id: '53',
    invoiceNo: 'INV-REPLACEMENT-53',
    totalCent: 5000,
    replacementForId: oldBlue.id,
  })
  const wrapper = page(InvoiceDetail, [
    'mall.invoices.read',
    'mall.invoices.write',
  ])
  await flushPromises()
  expect(wrapper.find('[data-test="reissue-blue-51"]').exists()).toBe(true)
  await wrapper.vm.beginReplacement(oldBlue)
  expect(wrapper.vm.issueForm.sellerIdentity).toBe('北京鲁泰测试销售主体')
  await wrapper.vm.uploadBlueFile(
    new File(['replacement'], 'replacement.pdf', { type: 'application/pdf' })
  )
  Object.assign(wrapper.vm.issueForm, {
    invoiceNo: 'INV-REPLACEMENT-53',
    issuedAt: '2026-11-07T11:00:00Z',
  })
  await wrapper.vm.recordBlue()
  expect(api.recordMallInvoice).toHaveBeenCalledWith(
    expect.objectContaining({
      id: '8',
      expectedVersion: 3,
      invoiceNo: 'INV-REPLACEMENT-53',
      sellerIdentity: '北京鲁泰测试销售主体',
      totalCent: 5000,
      fileId: '120',
      replacementForId: '51',
    }),
    expect.any(String)
  )
  wrapper.unmount()
})

it('replaces a lost PDF on the same invoice without recording a new tax ticket', async () => {
  api.getAdminMallInvoiceRequest.mockResolvedValueOnce({
    ...structuredClone(invoiceRequest),
    status: 'delivered',
    claimedBy: '31',
    invoices: [structuredClone(blueInvoice)],
    invoiceIds: ['51'],
    version: 2,
  })
  api.uploadInvoicePdf.mockResolvedValue({ id: '121', status: 'verified' })
  api.replaceMallInvoiceFile.mockResolvedValue({
    ...structuredClone(blueInvoice),
    fileId: '121',
    version: 2,
  })
  const wrapper = page(InvoiceDetail, [
    'mall.invoices.read',
    'mall.invoices.write',
  ])
  await flushPromises()
  wrapper.vm.activeFileInvoiceId = '51'
  await wrapper.vm.uploadReplacementFile(
    '51',
    new File(['replacement pdf'], 'replacement.pdf', {
      type: 'application/pdf',
    })
  )
  wrapper.vm.replacementReason = '原下载文件损坏，补交清晰副本'
  await wrapper.vm.replaceFile('51')
  expect(api.replaceMallInvoiceFile).toHaveBeenCalledWith(
    {
      id: '51',
      expectedVersion: 1,
      fileId: '121',
      reason: '原下载文件损坏，补交清晰副本',
    },
    expect.any(String)
  )
  expect(api.recordMallInvoice).not.toHaveBeenCalled()
  wrapper.unmount()
})

it('sends invoice PDF bytes through the API and reuses the same file intent on retry', async () => {
  const actual = await vi.importActual('@/api/mall-invoices')
  const randomUUID = globalThis.crypto.randomUUID.bind(globalThis.crypto)
  vi.stubGlobal('crypto', {
    randomUUID,
    subtle: {
      digest: vi.fn(async () => new Uint8Array(32).buffer),
    },
  })
  const file = new File(['verified bytes'], 'issued-invoice.pdf', {
    type: 'application/pdf',
  })
  file.arrayBuffer = vi.fn().mockResolvedValue(new Uint8Array([1, 2, 3]).buffer)
  httpMocks.post
    .mockResolvedValueOnce({
      data: {
        data: {
          fileId: '120',
          uploadUrl: 'https://storage.example.test/private-ticket',
        },
      },
    })
    .mockResolvedValueOnce({
      data: { data: { id: '120', status: 'verified' } },
    })
    .mockResolvedValueOnce({
      data: { data: { id: '120', status: 'verified' } },
    })
  const state = actual.createInvoicePdfUploadState(file, '9')
  const verified = await actual.uploadInvoicePdf(state)

  expect(verified).toEqual({ id: '120', status: 'verified' })
  expect(httpMocks.post.mock.calls[0][1]).toMatchObject({
    purpose: 'invoice_pdf',
    orderId: '9',
    fileName: 'issued-invoice.pdf',
    contentType: 'application/pdf',
    fileSize: file.size,
    sha256: '0'.repeat(64),
  })
  expect(httpMocks.post).toHaveBeenNthCalledWith(
    2,
    '/admin/mall/files/120/verify',
    file,
    expect.objectContaining({
      headers: { 'Content-Type': 'application/pdf', 'Idempotency-Key': state.verifyKey },
    })
  )

  await actual.uploadInvoicePdf(state)
  expect(httpMocks.post).toHaveBeenCalledTimes(3)
  expect(httpMocks.post.mock.calls[2][0]).toBe('/admin/mall/files/120/verify')
  expect(httpMocks.post.mock.calls[2][2].headers['Idempotency-Key']).toBe(
    state.verifyKey
  )
})

it('rejects a non-PDF or oversize file before creating a storage ticket', async () => {
  const actual = await vi.importActual('@/api/mall-invoices')
  const state = actual.createInvoicePdfUploadState(
    new File(['image'], 'wrong.png', { type: 'image/png' }),
    '9'
  )
  await expect(actual.uploadInvoicePdf(state)).rejects.toThrow('PDF')
  expect(httpMocks.post).not.toHaveBeenCalled()
})

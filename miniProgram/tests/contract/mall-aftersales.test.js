const test = require('node:test')
const assert = require('node:assert/strict')

const { createMallAftersaleService } = require('../../services/mall-aftersale-service')

function fixture(options = {}) {
  const calls = []
  const uploads = []
  const requests = []
  const service = createMallAftersaleService({
    getAccessToken: options.getAccessToken || (() => 'buyer-token'),
    request: async (apiPath, requestOptions = {}) => {
      calls.push({ apiPath, options: requestOptions })
      if (apiPath.endsWith('/upload-ticket')) return {
        fileId: '31',
        uploadUrl: 'https://bucket-1.cos.ap-beijing.myqcloud.com/mall/proof?signature=temporary'
      }
      if (apiPath.endsWith('/verify')) return { id: '31', status: 'verified', version: 2 }
      return options.response || { id: '21', orderId: '9', status: 'submitted', version: 1 }
    },
    uploadAdapter: async (uploadUrl, filePath, contentType, data) => {
      uploads.push({ uploadUrl, filePath, contentType, data })
      return { statusCode: 204 }
    },
    readFileAdapter: async (filePath) => {
      requests.push(filePath)
      return Uint8Array.from([97, 98, 99]).buffer
    }
  })
  return { service, calls, uploads, requests }
}

const baseApplication = {
  orderId: '9',
  expectedOrderVersion: 4,
  method: 'refund_only',
  items: [{ orderItemId: '14', quantity: 2 }],
  reason: '商品有质量问题',
  description: '外包装破损',
  proofFileIds: ['31']
}

test('requires a buyer session before reading or changing private aftersales', async () => {
  const f = fixture({ getAccessToken: () => '' })
  assert.throws(() => f.service.listMyMallAftersales(), (error) => {
    assert.equal(error.kind, 'AUTH')
    return true
  })
  assert.throws(() => f.service.createMallAftersale(baseApplication, 'mall-after-apply-0001'), (error) => {
    assert.equal(error.kind, 'AUTH')
    return true
  })
  assert.equal(f.calls.length, 0)
})

test('uses buyer aftersale contracts and preserves idempotency keys for retries', async () => {
  const f = fixture()
  await f.service.listMyMallAftersales({ pageSize: 10, cursor: 'opaque+/=' })
  await f.service.getMyMallAftersale('21')
  await f.service.createMallAftersale(baseApplication, 'mall-after-apply-0001')
  await f.service.withdrawMallAftersale('21', { expectedVersion: 2, reason: '不再需要' }, 'mall-after-withdraw-01')
  await f.service.sendMallReturn('21', {
    expectedVersion: 3,
    courierCode: 'SF',
    trackingNo: 'SF12345678'
  }, 'mall-after-return-0001')

  assert.deepEqual(f.calls, [
    {
      apiPath: '/api/v1/mall/aftersales',
      options: { data: { pageSize: 10, cursor: 'opaque+/=' } }
    },
    { apiPath: '/api/v1/mall/aftersales/21', options: {} },
    {
      apiPath: '/api/v1/mall/aftersales',
      options: {
        method: 'POST',
        data: {
          orderId: '9', expectedOrderVersion: 4, method: 'refund_only',
          items: [{ orderItemId: '14', quantity: 2 }], reason: '商品有质量问题',
          description: '外包装破损', proofFileIds: ['31'], scope: 'goods'
        },
        idempotencyKey: 'mall-after-apply-0001'
      }
    },
    {
      apiPath: '/api/v1/mall/aftersales/21/withdraw',
      options: {
        method: 'POST', data: { expectedVersion: 2, reason: '不再需要' },
        idempotencyKey: 'mall-after-withdraw-01'
      }
    },
    {
      apiPath: '/api/v1/mall/aftersales/21/return-shipment',
      options: {
        method: 'POST',
        data: { expectedVersion: 3, courierCode: 'SF', trackingNo: 'SF12345678' },
        idempotencyKey: 'mall-after-return-0001'
      }
    }
  ])

  await f.service.createMallAftersale(baseApplication, 'mall-after-apply-0001')
  assert.equal(f.calls.at(-1).options.idempotencyKey, 'mall-after-apply-0001')
  assert.deepEqual(f.calls.at(-1).options.data, f.calls[2].options.data)
})

test('uploads private aftersale proofs through ticket, direct PUT and verification', async () => {
  const f = fixture()
  await f.service.getAftersaleProofUploadTicket({
    orderId: '9', fileName: '包装破损.jpg', contentType: 'image/jpeg',
    filePath: '/tmp/proof.jpg', fileSize: 3
  }, 'mall-proof-ticket-0001')
  const uploadUrl = 'https://bucket-1.cos.ap-beijing.myqcloud.com/mall/proof?signature=temporary'
  await f.service.uploadAftersaleProofFile(uploadUrl, '/tmp/proof.jpg', 'image/jpeg')
  await f.service.verifyAftersaleProof('31', 'mall-proof-verify-0001')

  assert.deepEqual(f.calls, [
    {
      apiPath: '/api/v1/mall/files/upload-ticket',
      options: {
        method: 'POST', idempotencyKey: 'mall-proof-ticket-0001',
        data: {
          purpose: 'aftersale_proof', orderId: '9', fileName: '包装破损.jpg',
          contentType: 'image/jpeg', fileSize: 3,
          sha256: 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'
        }
      }
    },
    {
      apiPath: '/api/v1/mall/files/31/verify',
      options: { method: 'POST', idempotencyKey: 'mall-proof-verify-0001' }
    }
  ])
  assert.deepEqual(f.uploads, [{
    uploadUrl, filePath: '/tmp/proof.jpg',
    contentType: 'image/jpeg', data: Uint8Array.from([97, 98, 99]).buffer
  }])
})

test('validates IDs, quantities, reasons, proof metadata, keys and return fields before transport', async () => {
  const f = fixture()
  assert.throws(() => f.service.getMyMallAftersale('../21'))
  assert.throws(() => f.service.listMyMallAftersales({ pageSize: 101 }))
  assert.throws(() => f.service.createMallAftersale({ ...baseApplication, items: [{ orderItemId: '14', quantity: 0 }] }, 'mall-after-apply-0001'))
  assert.throws(() => f.service.createMallAftersale({ ...baseApplication, items: [{ orderItemId: '14', quantity: 1 }, { orderItemId: '14', quantity: 2 }] }, 'mall-after-apply-0001'))
  assert.throws(() => f.service.createMallAftersale({ ...baseApplication, scope: 'freight_only' }, 'mall-after-apply-0001'))
  assert.throws(() => f.service.createMallAftersale(baseApplication, 'short'))
  assert.throws(() => f.service.sendMallReturn('21', { expectedVersion: 2, courierCode: '中通', trackingNo: '123' }, 'mall-after-return-0001'))
  await assert.rejects(
    f.service.getAftersaleProofUploadTicket({
      orderId: '9', fileName: 'proof.jpg', contentType: 'image/gif', fileSize: 4096, sha256: 'bad'
    }, 'mall-proof-ticket-0001'),
    (error) => error.kind === 'VALIDATION'
  )
  await assert.rejects(
    f.service.getAftersaleProofUploadTicket({
      orderId: '9', fileName: 'proof.jpg', contentType: 'image/jpeg',
      filePath: '/tmp/proof.jpg', fileSize: 4096
    }, 'mall-proof-ticket-0002'),
    (error) => error.kind === 'VALIDATION'
  )
  await assert.rejects(
    f.service.uploadAftersaleProofFile('https://attacker.example/collect', '/tmp/proof.jpg', 'image/jpeg'),
    (error) => error.kind === 'VALIDATION'
  )
  assert.equal(f.calls.length, 0)
  assert.equal(f.uploads.length, 0)
})

test('keeps aftersale, refund and invoice progress as separate facts', () => {
  const f = fixture()
  assert.deepEqual(f.service.getFinancialProgress({
    status: 'completed', refundId: '88', refundStatus: 'succeeded'
  }), {
    aftersaleStatus: 'completed', refundId: '88', refundStatus: 'succeeded', invoiceStatus: 'not_exposed'
  })
  assert.deepEqual(f.service.getFinancialProgress({ status: 'awaiting_refund', refundId: null }), {
    aftersaleStatus: 'awaiting_refund', refundId: null, refundStatus: 'not_exposed', invoiceStatus: 'not_exposed'
  })
})

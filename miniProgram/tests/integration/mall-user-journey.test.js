const test = require('node:test')
const assert = require('node:assert/strict')

const { createMallCheckoutService } = require('../../services/mall-checkout-service')
const { createMallPaymentService } = require('../../services/mall-payment-service')
const { createMallOrderService } = require('../../services/mall-order-service')
const { createMallAftersaleService } = require('../../services/mall-aftersale-service')
const { createMallInvoiceService } = require('../../services/mall-invoice-service')

test('synthetic buyer journey keeps one order through canceled/unknown payment, recovery, logistics, aftersale and private invoice access', async () => {
  const calls = []
  const token = 'synthetic-buyer-token'
  let paymentStatus = 'unknown'
  let orderStatus = 'pending_payment'
  let orderVersion = 1
  const order = {
    id: '31',
    get version() { return orderVersion },
    get status() { return orderStatus },
    get paymentStatus() { return paymentStatus }
  }
  const request = async (path, options = {}) => {
    const method = options.method || 'GET'
    calls.push({ path, method, options })

    if (path === '/api/v1/mall/checkout/settings') {
      return { purchasingAvailable: true, policyVersion: 'policy-test-v1' }
    }
    if (path === '/api/v1/mall/checkout/quote') {
      return { quoteToken: 'synthetic-quote', payableAmountCent: 990, policyVersion: 'policy-test-v1' }
    }
    if (path === '/api/v1/mall/orders' && method === 'POST') {
      return { ...order }
    }
    if (path === '/api/v1/mall/orders/31/payment' && method === 'POST') {
      return {
        canInvoke: true,
        invokeParams: {
          timeStamp: '1', nonceStr: 'synthetic', package: 'prepay_id=synthetic',
          signType: 'RSA', paySign: 'synthetic-signature'
        }
      }
    }
    if (path === '/api/v1/mall/orders/31/payment') return { status: paymentStatus }
    if (path === '/api/v1/mall/orders/31') return { id: order.id, version: order.version, status: order.status, paymentStatus: order.paymentStatus }
    if (path === '/api/v1/mall/orders/31/logistics') {
      return { orderId: '31', source: null, queryStatus: 'config_required', events: [] }
    }
    if (path === '/api/v1/mall/aftersales' && method === 'POST') {
      return { id: '51', orderId: '31', status: 'pending_review' }
    }
    if (path === '/api/v1/mall/invoice-requests' && method === 'POST') {
      return { id: '61', orderId: '31', status: 'pending' }
    }
    if (path === '/api/v1/mall/files/93/access') {
      return { accessUrl: 'https://private.example/synthetic.pdf?temporary=one' }
    }
    throw new Error(`Unexpected synthetic request: ${method} ${path}`)
  }

  const options = { request, getAccessToken: () => token }
  const checkout = createMallCheckoutService(options)
  const payment = createMallPaymentService({
    ...options,
    requestPayment: async () => { throw new Error('requestPayment:fail cancel') }
  })
  const orders = createMallOrderService(options)
  const aftersales = createMallAftersaleService(options)
  const invoices = createMallInvoiceService(options)

  const settings = await checkout.getCheckoutSettings()
  assert.equal(settings.purchasingAvailable, true)
  const quote = await checkout.quoteOrder({ addressId: '8', items: [{ skuId: '11', quantity: 1 }] })
  const created = await checkout.createOrder({
    quoteToken: quote.quoteToken,
    consentVersion: quote.policyVersion,
    consentConfirmed: true,
    invoiceIntent: true
  }, 'mall-order-journey-key-0001')

  const paymentResult = await payment.payOrder(created.id, created.version, 'mall-pay-journey-key-0001')
  assert.equal(paymentResult.requestPaymentOutcome, 'cancelled')
  assert.equal(paymentResult.status, 'unknown')
  // Simulate a verified success fact arriving asynchronously in the fake backend.
  paymentStatus = 'succeeded'
  orderStatus = 'pending_receipt'
  orderVersion = 2
  const recoveredPayment = await payment.reconcilePayment(created.id)
  assert.equal(recoveredPayment.status, 'succeeded')

  const orderDetail = await orders.getMyMallOrder(created.id)
  const logistics = await orders.getMyMallLogistics(orderDetail.id)
  assert.equal(logistics.queryStatus, 'config_required')

  const aftersale = await aftersales.createMallAftersale({
    orderId: orderDetail.id,
    expectedOrderVersion: orderDetail.version,
    method: 'refund_only',
    items: [{ orderItemId: '7', quantity: 1 }],
    reason: 'synthetic journey',
    scope: 'goods'
  }, 'mall-aftersale-journey-key-01')
  const invoice = await invoices.createMallInvoiceRequest({
    orderId: orderDetail.id,
    expectedOrderVersion: orderDetail.version,
    buyerType: 'personal',
    title: '测试购买者',
    invoiceType: 'digital_normal',
    consentVersion: 'invoice-policy-test-v1',
    consentConfirmed: true
  }, 'mall-invoice-journey-key-01')
  const privateFile = await invoices.getMallInvoiceFileAccess('93')

  assert.equal(aftersale.orderId, created.id)
  assert.equal(invoice.orderId, created.id)
  assert.match(privateFile.accessUrl, /^https:\/\/private\.example\//)
  assert.equal(calls.filter((call) => call.path === '/api/v1/mall/orders' && call.method === 'POST').length, 1)
  assert.equal(calls.filter((call) => call.path === '/api/v1/mall/orders/31/payment' && call.method === 'POST').length, 1)
  assert.ok(calls.every((call) => call.options.auth !== false || call.path === '/api/v1/mall/checkout/settings'))
})

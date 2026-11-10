# 任务追踪：自营独立商城

本表仅表示计划覆盖，不代表接口、测试或验收已完成。操作来自当前OpenAPI（已纳入快递100补充），详细依赖见[tasks.md](tasks.md)与[tasks-map.json](tasks-map.json)。

## 106个操作归属

| operationId | 方法/路径 | 实现任务 | 条件 |
|---|---|---|---|
| `listMallCategories` | GET `/api/v1/mall/categories` | T032 | 通用实时授权/状态/幂等 |
| `listMallProducts` | GET `/api/v1/mall/products` | T032 | 通用实时授权/状态/幂等 |
| `getMallProduct` | GET `/api/v1/mall/products/{productId}` | T032 | 通用实时授权/状态/幂等 |
| `getMallCheckoutSettings` | GET `/api/v1/mall/checkout/settings` | T047 | 公开仅返回购买开关、运费策略与当前规则版本；no-store |
| `listMallAddresses` | GET `/api/v1/mall/addresses` | T047 | 通用实时授权/状态/幂等 |
| `createMallAddress` | POST `/api/v1/mall/addresses` | T047 | 通用实时授权/状态/幂等 |
| `updateMallAddress` | PATCH `/api/v1/mall/addresses/{addressId}` | T047 | 通用实时授权/状态/幂等 |
| `archiveMallAddress` | POST `/api/v1/mall/addresses/{addressId}/archive` | T047 | 通用实时授权/状态/幂等 |
| `getMallCart` | GET `/api/v1/mall/cart` | T047 | 通用实时授权/状态/幂等 |
| `addMallCartItem` | POST `/api/v1/mall/cart` | T047 | 通用实时授权/状态/幂等 |
| `updateMallCartItem` | PATCH `/api/v1/mall/cart/{cartItemId}` | T047 | 通用实时授权/状态/幂等 |
| `removeMallCartItem` | POST `/api/v1/mall/cart/{cartItemId}/remove` | T047 | 通用实时授权/状态/幂等 |
| `quoteMallOrder` | POST `/api/v1/mall/checkout/quote` | T047 | 通用实时授权/状态/幂等 |
| `createMallOrder` | POST `/api/v1/mall/orders` | T047 | 通用实时授权/状态/幂等 |
| `listMyMallOrders` | GET `/api/v1/mall/orders` | T047 | 通用实时授权/状态/幂等 |
| `getMyMallOrder` | GET `/api/v1/mall/orders/{orderId}` | T047 | 通用实时授权/状态/幂等 |
| `cancelMallOrder` | POST `/api/v1/mall/orders/{orderId}/cancel` | T047 | 通用实时授权/状态/幂等 |
| `prepareMallPayment` | POST `/api/v1/mall/orders/{orderId}/payment` | T047 | 通用实时授权/状态/幂等 |
| `getMallPayment` | GET `/api/v1/mall/orders/{orderId}/payment` | T047 | 通用实时授权/状态/幂等 |
| `confirmMallReceipt` | POST `/api/v1/mall/orders/{orderId}/confirm-receipt` | T062 | 通用实时授权/状态/幂等 |
| `changeMallOrderAddress` | PATCH `/api/v1/mall/orders/{orderId}/address` | T047 | 通用实时授权/状态/幂等 |
| `createMallAftersale` | POST `/api/v1/mall/aftersales` | T072 | 通用实时授权/状态/幂等 |
| `listMyMallAftersales` | GET `/api/v1/mall/aftersales` | T072 | 通用实时授权/状态/幂等 |
| `getMyMallAftersale` | GET `/api/v1/mall/aftersales/{aftersaleId}` | T072 | 通用实时授权/状态/幂等 |
| `withdrawMallAftersale` | POST `/api/v1/mall/aftersales/{aftersaleId}/withdraw` | T072 | 通用实时授权/状态/幂等 |
| `sendMallReturn` | POST `/api/v1/mall/aftersales/{aftersaleId}/return-shipment` | T072 | 通用实时授权/状态/幂等 |
| `createMallInvoiceRequest` | POST `/api/v1/mall/invoice-requests` | T101 | 通用实时授权/状态/幂等 |
| `getMyMallInvoiceRequest` | GET `/api/v1/mall/invoice-requests/{requestId}` | T101 | 通用实时授权/状态/幂等 |
| `updateMyMallInvoiceRequest` | PATCH `/api/v1/mall/invoice-requests/{requestId}` | T101 | 通用实时授权/状态/幂等 |
| `withdrawMallInvoiceRequest` | POST `/api/v1/mall/invoice-requests/{requestId}/withdraw` | T101 | 通用实时授权/状态/幂等 |
| `listMyMallInvoices` | GET `/api/v1/mall/orders/{orderId}/invoices` | T101 | 通用实时授权/状态/幂等 |
| `requestMallInvoiceCorrection` | POST `/api/v1/mall/invoices/{invoiceId}/correction` | T101 | 通用实时授权/状态/幂等 |
| `getBuyerMallUploadTicket` | POST `/api/v1/mall/files/upload-ticket` | T025 | 通用实时授权/状态/幂等 |
| `verifyBuyerMallFile` | POST `/api/v1/mall/files/{fileId}/verify` | T025 | 通用实时授权/状态/幂等 |
| `getBuyerMallFileAccess` | GET `/api/v1/mall/files/{fileId}/access` | T025 | 通用实时授权/状态/幂等 |
| `getAdminMallWorkbench` | GET `/api/v1/admin/mall/workbench` | T123 | 通用实时授权/状态/幂等 |
| `listAdminMallCategorys` | GET `/api/v1/admin/mall/categories` | T032 | 通用实时授权/状态/幂等 |
| `createAdminMallCategory` | POST `/api/v1/admin/mall/categories` | T032 | 通用实时授权/状态/幂等 |
| `updateAdminMallCategory` | PATCH `/api/v1/admin/mall/categories/{categoryId}` | T032 | 通用实时授权/状态/幂等 |
| `listAdminMallProducts` | GET `/api/v1/admin/mall/products` | T032 | 通用实时授权/状态/幂等 |
| `createAdminMallProduct` | POST `/api/v1/admin/mall/products` | T032 | 通用实时授权/状态/幂等 |
| `updateAdminMallProduct` | PATCH `/api/v1/admin/mall/products/{productId}` | T032 | 通用实时授权/状态/幂等 |
| `getAdminMallProduct` | GET `/api/v1/admin/mall/products/{productId}` | T032 | 通用实时授权/状态/幂等 |
| `setMallProductStatus` | POST `/api/v1/admin/mall/products/{productId}/status` | T032 | 通用实时授权/状态/幂等 |
| `copyMallProduct` | POST `/api/v1/admin/mall/products/{productId}/copy` | T032 | 通用实时授权/状态/幂等 |
| `adjustMallStock` | POST `/api/v1/admin/mall/skus/{skuId}/stock-adjustments` | T032 | 通用实时授权/状态/幂等 |
| `listMallStockMovements` | GET `/api/v1/admin/mall/skus/{skuId}/stock-movements` | T032 | 通用实时授权/状态/幂等 |
| `listAdminMallOrders` | GET `/api/v1/admin/mall/orders` | T062 | 通用实时授权/状态/幂等 |
| `getAdminMallOrder` | GET `/api/v1/admin/mall/orders/{orderId}` | T062 | 通用实时授权/状态/幂等 |
| `noteMallOrder` | PATCH `/api/v1/admin/mall/orders/{orderId}/note` | T062 | 通用实时授权/状态/幂等 |
| `cancelAdminMallOrder` | POST `/api/v1/admin/mall/orders/{orderId}/cancel` | T062 | 通用实时授权/状态/幂等 |
| `shipMallOrder` | POST `/api/v1/admin/mall/orders/{orderId}/ship` | T062 | 通用实时授权/状态/幂等 |
| `releaseMallFulfillment` | POST `/api/v1/admin/mall/orders/{orderId}/fulfillment-release` | T063 | governance-proposal.md:资料目的限定窄例外未生效时关闭 |
| `correctMallTracking` | PATCH `/api/v1/admin/mall/shipments/{shipmentId}` | T062 | 通用实时授权/状态/幂等 |
| recordMallPlatformShipmentReport | POST /api/v1/admin/mall/shipments/{shipmentId}/platform-report | T056 | 通用实时授权/状态/幂等；只登记管理员的微信后台手工录入确认，不调用微信API |
| `listAdminMallAftersales` | GET `/api/v1/admin/mall/aftersales` | T072 | 通用实时授权/状态/幂等 |
| `getAdminMallAftersale` | GET `/api/v1/admin/mall/aftersales/{aftersaleId}` | T072 | 通用实时授权/状态/幂等 |
| `decideMallAftersale` | POST `/api/v1/admin/mall/aftersales/{aftersaleId}/decision` | T072 | 通用实时授权/状态/幂等 |
| `receiveMallReturn` | POST `/api/v1/admin/mall/aftersales/{aftersaleId}/receipt` | T072 | 通用实时授权/状态/幂等 |
| `executeMallRefund` | POST `/api/v1/admin/mall/aftersales/{aftersaleId}/execute-refund` | T072 | 通用实时授权/状态/幂等 |
| `listAdminMallPayments` | GET `/api/v1/admin/mall/payments` | T112 | 通用实时授权/状态/幂等 |
| `getAdminMallPayment` | GET `/api/v1/admin/mall/payments/{paymentId}` | T112 | 通用实时授权/状态/幂等 |
| `queryMallPayment` | POST `/api/v1/admin/mall/payments/{paymentId}/query` | T112 | 通用实时授权/状态/幂等 |
| `exportMallPayment` | POST `/api/v1/admin/mall/payments/export` | T112 | 通用实时授权/状态/幂等 |
| `listAdminMallRefunds` | GET `/api/v1/admin/mall/refunds` | T073 | 通用实时授权/状态/幂等；G-PROTOCOL例外仅适用于两个通知入口 |
| `getAdminMallRefund` | GET `/api/v1/admin/mall/refunds/{refundId}` | T073 | 通用实时授权/状态/幂等；G-PROTOCOL仅限制通知子项 |
| `queryMallRefund` | POST `/api/v1/admin/mall/refunds/{refundId}/query` | T073 | 通用实时授权/状态/幂等；G-PROTOCOL仅限制通知子项 |
| `exportMallRefund` | POST `/api/v1/admin/mall/refunds/export` | T112 | 通用实时授权/状态/幂等 |
| `getAdminMallFinanceExport` | GET `/api/v1/admin/mall/finance/exports/{requestId}` | T112 | 通用实时授权/状态/幂等；只返回本人授权异步导出状态 |
| `retryMallRefund` | POST `/api/v1/admin/mall/refunds/{refundId}/retry` | T073 | 通用实时授权/状态/幂等；G-PROTOCOL仅限制通知子项 |
| `listAdminMallInvoiceRequests` | GET `/api/v1/admin/mall/invoice-requests` | T101 | 通用实时授权/状态/幂等 |
| `getAdminMallInvoiceRequest` | GET `/api/v1/admin/mall/invoice-requests/{requestId}` | T101 | 通用实时授权/状态/幂等 |
| `releaseMallBilling` | POST `/api/v1/admin/mall/invoice-requests/{requestId}/billing-release` | T102 | governance-proposal.md:资料目的限定窄例外未生效时关闭 |
| `claimMallInvoice` | POST `/api/v1/admin/mall/invoice-requests/{requestId}/claim` | T101 | 通用实时授权/状态/幂等 |
| `needMallInvoiceInfo` | POST `/api/v1/admin/mall/invoice-requests/{requestId}/needs-info` | T101 | 通用实时授权/状态/幂等 |
| `recordMallInvoice` | POST `/api/v1/admin/mall/invoice-requests/{requestId}/record` | T101 | 通用实时授权/状态/幂等 |
| `replaceMallInvoiceFile` | PATCH `/api/v1/admin/mall/invoices/{invoiceId}/file` | T101 | 通用实时授权/状态/幂等 |
| `recordMallRedInvoice` | POST `/api/v1/admin/mall/invoices/{invoiceId}/red-record` | T101 | 通用实时授权/状态/幂等 |
| `markMallRedPending` | POST `/api/v1/admin/mall/invoices/{invoiceId}/red-pending` | T101 | 通用实时授权/状态/幂等 |
| `getAdminMallUploadTicket` | POST `/api/v1/admin/mall/files/upload-ticket` | T025 | 通用实时授权/状态/幂等 |
| `verifyAdminMallFile` | POST `/api/v1/admin/mall/files/{fileId}/verify` | T025 | 通用实时授权/状态/幂等 |
| `getAdminMallFileAccess` | GET `/api/v1/admin/mall/files/{fileId}/access` | T025 | 通用实时授权/状态/幂等 |
| `listAdminMallConsumptions` | GET `/api/v1/admin/mall/consumptions` | T085 | 通用实时授权/状态/幂等 |
| `attributeMallConsumption` | POST `/api/v1/admin/mall/consumptions/{consumptionId}/attribution` | T088 | 通用实时授权/状态/幂等 |
| `listPerformanceAdjustments` | GET `/api/v1/admin/performance/adjustments` | T091 | 通用实时授权/状态/幂等 |
| `getPerformanceAdjustment` | GET `/api/v1/admin/performance/adjustments/{adjustmentId}` | T091 | 通用实时授权/状态/幂等 |
| `reviewPerformanceAdjustment` | POST `/api/v1/admin/performance/adjustments/{adjustmentId}/review` | T091 | 通用实时授权/状态/幂等 |
| `rejectPerformanceAdjustment` | POST `/api/v1/admin/performance/adjustments/{adjustmentId}/reject` | T091 | 通用实时授权/状态/幂等 |
| `reconcilePerformanceAdjustment` | POST `/api/v1/admin/performance/adjustments/{adjustmentId}/reconcile` | T091 | 通用实时授权/状态/幂等 |
| `getPerformanceNetEntitlement` | GET `/api/v1/admin/performance/results/{resultId}/net-entitlement` | T091 | 通用实时授权/状态/幂等 |
| `createMallReconciliation` | POST `/api/v1/admin/mall/reconciliations` | T112 | 通用实时授权/状态/幂等 |
| `listMallReconciliations` | GET `/api/v1/admin/mall/reconciliations` | T112 | 通用实时授权/状态/幂等 |
| `getMallReconciliation` | GET `/api/v1/admin/mall/reconciliations/{batchId}` | T112 | 通用实时授权/状态/幂等 |
| `addMallDifference` | POST `/api/v1/admin/mall/reconciliations/{batchId}/differences` | T112 | 通用实时授权/状态/幂等 |
| `listMallDifferences` | GET `/api/v1/admin/mall/reconciliations/{batchId}/differences` | T112 | 通用实时授权/状态/幂等 |
| `updateMallDifference` | PATCH `/api/v1/admin/mall/differences/{differenceId}` | T112 | 通用实时授权/状态/幂等 |
| `closeMallReconciliation` | POST `/api/v1/admin/mall/reconciliations/{batchId}/close` | T112 | 通用实时授权/状态/幂等 |
| `getMallSettings` | GET `/api/v1/admin/mall/settings` | T026 | 通用实时授权/状态/幂等 |
| `updateMallSettings` | PATCH `/api/v1/admin/mall/settings` | T026 | 通用实时授权/状态/幂等 |
| `getMyMallCommand` | GET `/api/v1/mall/commands/{commandId}` | T023 | 通用实时授权/状态/幂等 |
| `getAdminMallCommand` | GET `/api/v1/admin/mall/commands/{commandId}` | T023 | 通用实时授权/状态/幂等 |
| `wechatPaymentNotify` | POST `/api/v1/mall-gateway/wechat/payment-notify` | T048 | G-PROTOCOL |
| `wechatRefundNotify` | POST `/api/v1/mall-gateway/wechat/refund-notify` | T048 | G-PROTOCOL |
| `getMyMallLogistics` | GET `/api/v1/mall/orders/{orderId}/logistics` | T060 | 通用实时授权/状态/幂等 |
| `getAdminMallLogistics` | GET `/api/v1/admin/mall/orders/{orderId}/logistics` | T060 | 通用实时授权/状态/幂等 |
| `refreshMallLogistics` | POST `/api/v1/admin/mall/shipments/{shipmentId}/logistics-refresh` | T060 | 通用实时授权/状态/幂等 |

## 需求与验收覆盖

| 需求 | 直接任务（排除最终全量任务） |
|---|---|
| FR-001 | T028 |
| FR-002 | T029, T032, T035, T038, T114, T118, T125 |
| FR-003 | T026 |
| FR-004 | T039, T042, T047, T052, T116, T119 |
| FR-005 | T039, T042, T080, T088, T116, T119 |
| FR-006 | T034, T036, T037, T051, T066 |
| FR-007 | T033, T035, T064, T076, T105, T114, T117, T118, T125 |
| FR-008 | T080, T083 |
| FR-009 | T029, T030, T031, T032, T033, T035, T038 |
| FR-010 | T029, T030, T031, T032, T033, T035, T038 |
| FR-011 | T029, T030, T031, T032, T033, T035, T037, T038 |
| FR-012 | T029, T030, T031, T032, T033, T035, T038 |
| FR-013 | T030, T031, T032, T033, T035, T038, T041, T043, T052 |
| FR-014 | T030, T031, T032, T033, T035, T038 |
| FR-015 | T029, T030, T031, T032, T033, T035, T038 |
| FR-016 | T029, T030, T031, T032, T033, T035, T038, T043 |
| FR-017 | T029, T030, T031, T032, T033, T034, T035, T036, T037, T038 |
| FR-018 | T039, T042, T047, T050, T051, T052 |
| FR-019 | T039, T042, T047, T050, T051, T052 |
| FR-020 | T039, T043, T047, T049, T050, T051, T052 |
| FR-021 | T039, T043, T047, T049, T050, T051, T052 |
| FR-022 | T039, T041, T043, T047, T049, T050, T051, T052 |
| FR-023 | T039, T043, T047, T049, T050, T051, T052, T125 |
| FR-024 | T039, T041, T043, T046, T047, T049, T050, T051, T052, T062, T125 |
| FR-025 | T039, T043, T047, T049, T050, T051, T052, T053, T055, T062, T064, T067 |
| FR-026 | T040, T041, T044, T046, T047, T049, T050, T051, T052 |
| FR-027 | T040, T041, T044, T046, T047, T048, T049, T050, T051, T052 |
| FR-028 | T040, T041, T044, T046, T047, T048, T049, T050, T051, T052 |
| FR-029 | T040, T041, T045, T046, T047, T048, T049, T050, T051, T052 |
| FR-030 | T040, T041, T046, T047, T048, T049, T050, T051, T052 |
| FR-031 | T040, T041, T046, T048, T052 |
| FR-032 | T040, T046, T052, T109, T110, T112, T113, T114 |
| FR-033 | T040, T046, T052, T109, T110, T112, T113, T114 |
| FR-034 | T040, T046, T052, T109, T110, T112, T113, T114 |
| FR-035 | T040, T044, T046, T048, T052 |
| FR-036 | T047, T053, T055, T062, T064, T065, T066, T067 |
| FR-037 | T053, T054, T055, T056, T062, T064, T067 |
| FR-038 | T053, T055, T057, T058, T059, T060, T061, T062, T063, T064, T067, T116, T119, T120, T121 |
| FR-039 | T053, T054, T055, T056, T057, T058, T059, T060, T061, T062, T064, T065, T066, T067 |
| FR-040 | T053, T054, T055, T056, T057, T059, T060, T061, T062, T064, T067 |
| FR-041 | T053, T054, T055, T056, T057, T059, T060, T061, T062, T064, T065, T066, T067, T125 |
| FR-042 | T053, T054, T055, T056, T062, T064, T067, T079 |
| FR-043 | T068, T070, T072, T074, T075, T076, T077, T078, T079, T125 |
| FR-044 | T068, T070, T072, T074, T075, T076, T077, T078, T079 |
| FR-045 | T068, T070, T071, T072, T074, T075, T076, T077, T078, T079 |
| FR-046 | T068, T070, T071, T072, T074, T075, T076, T077, T078, T079 |
| FR-047 | T068, T070, T072, T074, T075, T076, T077, T078, T079 |
| FR-048 | T068, T070, T071, T072, T074, T075, T076, T077, T078, T079 |
| FR-049 | T059, T061, T068, T070, T071, T072, T074, T075, T076, T077, T078, T079 |
| FR-050 | T068, T069, T070, T071, T072, T073, T074, T075, T076, T077, T078, T079 |
| FR-051 | T069, T071, T072, T073, T074, T075, T076, T077, T078, T079, T109, T110, T112, T113, T114 |
| FR-052 | T069, T071, T072, T073, T074, T075, T076, T077, T078, T079 |
| FR-053 | T069, T071, T072, T073, T074, T075, T076, T077, T078, T079 |
| FR-054 | T068, T069, T070, T072, T073, T074, T075, T076, T077, T078, T079 |
| FR-055 | T068, T069, T070, T071, T072, T073, T074, T075, T076, T077, T078, T079, T122, T123 |
| FR-056 | T045, T046, T080, T083, T084, T085, T091, T092, T093, T094, T095, T096 |
| FR-057 | T080, T083, T084, T085, T087, T091, T092, T093, T094, T095, T096 |
| FR-058 | T045, T080, T083, T091, T092, T093, T094, T095, T096 |
| FR-059 | T045, T071, T079, T080, T083, T091, T092, T093, T094, T095, T096 |
| FR-060 | T045, T080, T083, T084, T088, T091, T092, T093, T094, T095, T096 |
| FR-061 | T080, T083, T084, T085, T088, T091, T092, T093, T094, T095, T096 |
| FR-062 | T080, T081, T083, T084, T086, T087, T091, T092, T093, T094, T095, T096 |
| FR-063 | T080, T081, T085, T086, T087, T090, T091, T092, T093, T094, T095, T096, T122 |
| FR-064 | T045, T071, T081, T082, T085, T086, T087, T088, T089, T090, T091, T092, T093, T094, T095, T096 |
| FR-065 | T081, T082, T086, T087, T089, T090, T091, T092, T093, T094, T095, T096 |
| FR-066 | T082, T089, T090, T091, T092, T093, T094, T095, T096 |
| FR-067 | T045, T046, T071, T079, T080, T081, T082, T083, T084, T085, T086, T087, T089, T090, T091, T092, T093, T094, T095, T096, T098, T100, T108 |
| FR-068 | T097, T099, T101, T103, T104, T105, T106, T107, T108 |
| FR-069 | T097, T099, T101, T102, T103, T104, T105, T106, T107, T108, T116, T119, T120, T121 |
| FR-070 | T097, T099, T101, T103, T104, T105, T106, T107, T108 |
| FR-071 | T097, T099, T101, T103, T104, T105, T106, T107, T108 |
| FR-072 | T097, T099, T101, T102, T103, T104, T105, T106, T107, T108 |
| FR-073 | T097, T098, T099, T100, T101, T103, T104, T105, T106, T107, T108 |
| FR-074 | T097, T098, T100, T101, T103, T104, T105, T106, T107, T108 |
| FR-075 | T097, T098, T100, T101, T103, T104, T105, T106, T107, T108 |
| FR-076 | T097, T098, T100, T101, T103, T104, T105, T106, T107, T108, T122, T123 |
| FR-077 | T097, T098, T100, T101, T102, T103, T104, T105, T106, T107, T108, T110, T112, T116, T120, T121 |
| FR-078 | T097, T099, T100, T101, T103, T104, T105, T106, T107, T108 |
| FR-079 | T097, T099, T100, T101, T103, T104, T105, T106, T107, T108, T125 |
| FR-080 | T109, T110, T111, T112, T113, T114, T115, T123, T125 |
| FR-081 | T109, T111, T112, T113, T114, T115, T125 |
| FR-082 | T109, T111, T112, T113, T114, T115, T122, T123, T124, T125 |
| FR-083 | T109, T110, T111, T112, T113, T114, T115, T125 |
| FR-084 | T122, T123, T124, T125, T126 |
| FR-085 | T122, T123, T124, T125, T126 |
| FR-086 | T063, T102, T116, T117, T118, T119, T120, T121 |
| FR-087 | T057, T059, T060, T061, T063, T084, T091, T094, T102, T116, T117, T118, T119, T120, T121 |
| FR-088 | T063, T102, T116, T117, T118, T119, T120, T121 |
| FR-089 | T044, T057, T058, T059, T061, T063, T098, T102, T116, T117, T118, T119, T120, T121, T124 |
| FR-090 | T033, T034, T035, T036, T037, T038, T049, T050, T051, T057, T059, T060, T061, T064, T065, T066, T074, T075, T076, T077, T078, T092, T093, T094, T095, T103, T104, T105, T106, T107, T113, T114, T116, T120, T121, T122, T124, T125, T126 |
| FR-091 | T048, T049, T050, T057, T059, T060, T061, T077, T106, T116, T120, T121, T124, T126 |
| FR-092 | T054, T056, T058, T119 |
| FR-093 | T037, T051, T066, T078, T095, T107 |
| FR-094 | T086, T096 |

| 验收 | 任务 |
|---|---|
| AC-001 | T029, T038 |
| AC-002 | T029, T030, T038 |
| AC-003 | T029, T030, T038 |
| AC-004 | T029, T030, T038 |
| AC-005 | T030, T038 |
| AC-006 | T030, T038 |
| AC-007 | T039, T052 |
| AC-008 | T039, T052 |
| AC-009 | T039, T041, T052 |
| AC-010 | T041, T052 |
| AC-011 | T039, T041, T052 |
| AC-012 | T040, T041, T052 |
| AC-013 | T040, T052 |
| AC-014 | T040, T041, T052 |
| AC-015 | T040, T052, T109 |
| AC-016 | T053, T067 |
| AC-017 | T053, T067 |
| AC-018 | T053, T067 |
| AC-019 | T068, T079 |
| AC-020 | T068, T079 |
| AC-021 | T068, T079 |
| AC-022 | T068, T079 |
| AC-023 | T068, T079 |
| AC-024 | T069, T079 |
| AC-025 | T068, T079 |
| AC-026 | T069, T079, T122 |
| AC-027 | T080, T096 |
| AC-028 | T080, T096 |
| AC-029 | T080, T081, T096 |
| AC-030 | T080, T082, T096 |
| AC-031 | T081, T082, T096 |
| AC-032 | T082, T096 |
| AC-033 | T081, T082, T096 |
| AC-034 | T097, T108 |
| AC-035 | T097, T108 |
| AC-036 | T097, T098, T108 |
| AC-037 | T097, T108 |
| AC-038 | T097, T098, T108 |
| AC-039 | T097, T098, T108, T116, T121 |
| AC-040 | T109, T115 |
| AC-041 | T122, T126 |
| AC-042 | T116, T121 |
| AC-043 | T003, T127, T131 |
| AC-044 | T130 |
| AC-045 | T128 |
| AC-046 | T057, T061 |
| AC-047 | T057, T061 |
| AC-048 | T057, T061 |
| AC-049 | T057, T061 |
| AC-050 | T057, T061 |
| AC-051 | T057, T061 |
| AC-052 | T006, T081, T082, T089, T096 |
| AC-053 | T053, T055, T062, T067 |

## 质量与分析修订追踪

更新：2026-11-09。以下区分本地/合成证据、现场/生产证据和整体质量目标；“本地通过”不表示真实平台、生产容量或投产门禁已通过。

| 质量项 | 验收要求 | 当前实际证据与状态 |
|---|---|---|
| Q-01 / SC-001 | AC-001–053逐例记录实际结果与证据，首期所有目标通过；超退、超卖、重复有效票/消费和越权成功为0 | **部分通过**。53项AC均有任务追踪；T128本地合成闭环10 passed、T129隔离MySQL与T130回归有记录；T048回调本地实现/隔离回归通过；T108发票本地合成闭环已完成；T131真实平台、T132真机/用户、T133经营发布材料及生产G-DATA配置仍未通过。依用户决策，商城不验证发票真伪。见[acceptance-results.md](acceptance-results.md)、[platform-acceptance.md](platform-acceptance.md)、[device-acceptance.md](device-acceptance.md)。 |
| Q-02 / SC-002 | 5名非开发用户；至少4名无需指导于180秒内到提交支付，外部等待另计 | **未验收**。本地40项页面集成测试通过；5名参与者、iOS/Android真机记录为空，不能据此通过易用性目标。见[device-acceptance.md](device-acceptance.md)。 |
| Q-03 / SC-003 | 500个在售商品、10,000历史订单、20并发用户，至少100次主要查询且95%在2秒内 | **未验收**。T129的并发窗口与单次耗时是隔离MySQL功能/竞争测量，不是此固定数据集的容量测试。见[performance-results.md](performance-results.md)。 |
| Q-04 / SC-004–005 | 100次末件争抢及各关键事实20次重放/乱序，金额、数量和唯一关联一致 | **本地部分通过**。T129记录100次末件提交尝试和幂等重放/恢复；T128合成交易检查唯一业务关联。完整的跨所有事实类型/乱序矩阵仍未作为一项整体验收。见[performance-results.md](performance-results.md)、[acceptance-results.md](acceptance-results.md)。 |
| Q-05 / SC-006 | 核实渠道结果后60秒内多端/待办一致；未知超过10分钟后形成责任异常 | **本地部分通过**。T126工作台和未知资金责任待办、T128合成资金结果有证据；真实渠道响应时间和生产多端SLO未测。 |
| Q-06 / SC-007–008 | 按F-02手算并核对展示/导出到分；冻结原值不动，调整累计正确 | **本地部分通过**。T096绩效/冻结/差额/核销闭环及T130既有系统回归通过；完整F-02人工样例与所有生产展示/导出逐项核对未形成总体签字。 |
| Q-07 / SC-009–010 | F-03及样例日账单核对；票据链和资金对应100%，未解决差异不关闭 | **本地部分通过**。T108合成发票申请/上传/下载及T128合成跨域和日对账验收已记录；发票上传由经办人确认有效，不做税务平台真伪验证；真实渠道日账单与生产COS仍未验收。见[acceptance-results.md](acceptance-results.md)。 |
| Q-08 / SC-011 | 买家、运营、履约、财务、组织角色及撤权场景；越权拒绝，敏感访问有审计且不含原文 | **内部实现通过，生产配置待办**。T116/T121有权限矩阵、撤权和跨买家回归；T063/T102覆盖单对象领取与元数据审计。生产访问等待留存引用和经审阅告知版本配置，外部传输仍未获批。 |
| Q-09 / SC-012 | 小程序视觉阶段前取得并记录本轮参考图和采用风格 | **设计输入已通过**。用户列表截图已归档，明确不显示“综合”，样式约定见[ui-reference.md](ui-reference.md)；这不代表T132真机视觉验收通过。 |
| Q-10 / FR-094 | 单命令准备独立MySQL、迁移、fixtures、自动化和清理；错误目标在建表前失败 | **本地隔离runner通过**。T005/T028的单命令隔离、所有权校验、失败非零退出和清理证据已记录；不代表生产数据库迁移已执行。见[quickstart.md](quickstart.md)、[implementation-log.md](implementation-log.md)。 |

## 当前任务状态与依赖边界

2026-11-09任务表与135项勾选已一致：**132项完成、3项进行中、0项待办**。未完成事项为：

- 待办：无。
- 进行中：T131、T132、T133。
- T052完成本地测试模式的地址至支付集成及恢复证据，T062完成本地订单/履约管理路由与AC-053；两者均不表示真实平台或商城整体发布已完成。T135完成本追踪核对也不替代其余门禁。

少数已完成任务的范围只覆盖经记录的独立切片：T062已完成本地订单/履约接口与权限；T054确定第一期通过微信后台手工录入、不接发货API；T056完成商城内人工登记状态回填，不代表微信后台真实账号能力已经验收。T064/T079/T116依赖本地接口/权限；T052和T128分别提供测试支付恢复与合成跨域AC-045证据，均不替代真实支付渠道验收。T108完成本地发票申请/经办确认上传/用户下载闭环；按用户决策不需要真实发票或税务平台真伪验证，生产COS仍由T131核验；T134只完成条件式文档，不打开T133发布门禁。不得把这些局部证据扩张成整项平台验收。

OpenAPI与追踪表核对结果：94条路径、106个HTTP操作、106个operationId及106个operation owner；94条FR、53项AC均在任务图中有覆盖；Q-01至Q-10在上表登记当前实际证据。两个通知operation归T048并仅使用已采纳G-PROTOCOL例外；recordMallPlatformShipmentReport归T056，只记录微信后台手工登记的管理员确认，不调用微信API或冒充平台回执；T063/T102仅按批准的内部范围实现，生产原文访问受配置门禁约束。

| 分析项 | 修订任务 | 剩余条件 |
|---|---|---|
| C1 通知协议 | T002、T048、T073、T131、T133 | 宪章3.0.0例外已采纳、协议已核验，T048本地实现/隔离回归通过；生产登记需G-LIVE授权 |
| C2 单命令环境 | T005、T028 | Q-10本地隔离runner已有证据；生产环境不适用 |
| I1 订单详情 | T053、T055、T062、T067 | AC-053本地/合成验收有证据；微信后台人工登记状态回填已由T056完成 |
| U1 无原结果调整 | T006、T012、T013、T018、T081、T082、T087–T091、T096 | AC-052本地闭环已记录；完整实际经营数据仍按发布准备核验 |
| I2 发货登记 | T054、T056、T131 | 第一期开通后台人工录入路径；商城状态回填已实现，真实账号验收仍由T131负责 |

旧接口兼容仍覆盖T083/T084统一来源、T085–T087月份与冻结、T090/T091净额核销及T130原功能回归，不建立钱包。

# 商城支付协议复核

更新：2026-11-12。用户明确要求商城微信支付继续使用 APIv2。此前记录的 APIv3 适配已由本决定替换；历史验收记录仍保留在 `implementation-log.md`，不代表当前支付适配器仍为 APIv3。

## 当前协议实现

| 能力 | 当前实现 | 官方依据 |
|---|---|---|
| JSAPI/小程序下单 | `POST /pay/unifiedorder`，XML 请求/响应；使用 `appid`、`mch_id`、商户单号、CNY 分金额、`openid`、终端 IP、失效时间和支付通知地址。 | [统一下单（APIv2）](https://pay.wechatpay.cn/doc/v2/merchant/4011936987) |
| 查单、关单 | `POST /pay/orderquery` 与 `POST /pay/closeorder`；响应按 APIv2 商户密钥验签，未签名、身份不符或含糊错误都不作为资金事实。 | [查询订单](https://pay.wechatpay.cn/doc/v2/merchant/4011987538)、[关闭订单](https://pay.wechatpay.cn/doc/v2/merchant/4011935216) |
| 原路退款、退款查询 | `POST /secapi/pay/refund` 使用商户双向证书；受理后再通过 `POST /pay/refundquery` 核对退款状态。两者均使用 APIv2 XML 签名。 | [申请退款](https://pay.wechatpay.cn/doc/v2/merchant/4011941262)、[查询退款](https://pay.wechatpay.cn/doc/v2/merchant/4011987766) |
| 小程序调起支付 | 使用 APIv2 `MD5` 或 `HMAC-SHA256` 对 `appId`、时间戳、随机串、`package` 和 `signType` 签名；签名类型需与统一下单保持一致。 | [小程序调起支付](https://pay.wechatpay.cn/doc/v2/merchant/4011939566) |
| 支付通知 | XML 通知体；按 APIv2 商户密钥校验 `sign`，匹配小程序、商户、订单号、付款人及金额后，持久提交事件和恢复任务，再返回 XML ACK。 | [支付结果通知](https://pay.wechatpay.cn/doc/v2/merchant/4011935221)、[签名算法](https://pay.wechatpay.cn/doc/v2/merchant/4011985891) |
| 退款通知 | XML 外层含加密的 `req_info`；按官方方式用 `MD5(APIv2 key)` 的小写十六进制文本作为 AES-256-ECB 密钥、PKCS7 解密，再核对本地退款和金额。 | [退款结果通知](https://pay.wechatpay.cn/doc/v2/merchant/4011985425) |

APIv2 不使用 APIv3 商户 RSA 私钥签名、平台公钥/证书验签或 APIv3 AES-GCM 通知密钥。APIv2 退款的双向 TLS 证书仍需要单独配置；APIv2 密钥和商户证书不是同一配置。

## 配置项

- `MALL_WECHAT_API_V2_KEY`：商户平台 APIv2 密钥，32 字节，保存在本地受控环境，不写入示例文件或日志。
- `MALL_WECHAT_API_V2_SIGN_TYPE`：`MD5`（默认）或 `HMAC-SHA256`。
- `MALL_WECHAT_SPBILL_CREATE_IP`：统一下单传给微信的服务器出口 IP。
- `MALL_WECHAT_NOTIFY_URL`、`MALL_WECHAT_REFUND_NOTIFY_URL`：公网 HTTPS 且不带 query 的支付/退款通知地址。
- `MALL_WECHAT_REFUND_CLIENT_CERT_PATH`、`MALL_WECHAT_REFUND_CLIENT_KEY_PATH`：APIv2 退款接口所需的商户双向证书及配对私钥文件路径。

APIv2 密钥轮换前应先停止通知接收并清空待处理的回调事件任务，再切换密钥；入箱事实的完整性 MAC 与接收时的 APIv2 密钥绑定。

订单预付令牌仍由 `MALL_PREPAY_KEYS` / `MALL_PREPAY_ACTIVE_KEY` 独立加密；它们不是微信 API 密钥。`MALL_GATEWAY_MODE`、资金出站、回调和 worker 开关仍控制执行，代码切换不会自动开启支付或调用商户平台。

## 恢复与安全边界

- XML 解析拒绝 DTD、实体声明、重复字段和超大正文；所有 API 请求固定 HTTPS 主机、禁止重定向及代理环境继承，并设响应大小和总截止时间。
- API 响应必须通过 APIv2 签名及 AppID/商户身份核对后，才可形成内部支付/退款事实。退款申请的受理响应不作为退款成功，之后必须查退款状态。
- 支付通知验证 APIv2 签名；退款通知解密 `req_info` 后再匹配退款单、原交易、金额及状态。支付通知入箱时检查 openid，持久化时不保留 openid 或原始 XML；最小化事实另以 APIv2 密钥派生的 HMAC 绑定事件类型、身份和原始正文摘要，worker 应用前再次核验。
- 只有事件和恢复任务同一事务提交后才向微信确认；成功/失败响应符合 APIv2 XML ACK 格式。重复通知可安全重放。
- 当前仍未进行真实商户联调、真实支付/退款、生产通知域名登记或部署。APIv2 配置需在本地受控环境逐项补齐后再验收。

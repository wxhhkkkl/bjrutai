# 外部支付通知协议：宪章例外与G-PROTOCOL

更新：2026-11-12。用户明确要求商城微信支付坚持使用 APIv2。此前 2026-11-09 对 APIv3 的协议核验与T048验收为历史记录，不再证明当前 APIv2 适配已验收。支付通知仍限于既有治理批准的两个入口；协议调整不启用生产通知或真实资金出站。

宪章版本由2.0.0升至3.0.0，见[宪章Sync Impact Report](../../.specify/memory/constitution.md)。宪章II继续要求所有项目业务API使用`{code,message,data,requestId,serverTime}`。唯一外部协议例外为以下两个POST入口：

- `/api/v1/mall-gateway/wechat/payment-notify`
- `/api/v1/mall-gateway/wechat/refund-notify`

两个入口不使用项目JWT和统一响应包装。例外不覆盖买家、后台、查单、退款执行、文件、物流、其它供应商或未来新增接口。

## APIv2官方协议

依据微信支付商户文档：[签名算法](https://pay.wechatpay.cn/doc/v2/merchant/4011985891)、[支付结果通知](https://pay.wechatpay.cn/doc/v2/merchant/4011935221)、[退款结果通知](https://pay.wechatpay.cn/doc/v2/merchant/4011985425)：

- 支付通知为 XML，使用 APIv2 商户密钥按 `MD5` 或 `HMAC-SHA256` 验证 `sign`；在状态应用前核对 AppID、商户号、订单号、币种、订单/实付金额、付款人 openid、渠道流水和支付时间。
- 退款通知为 XML，退款内容放在 `req_info`；先 Base64 解码，再对 APIv2 密钥取 MD5 小写十六进制文本，以 AES-256-ECB/PKCS7 解密，然后核对原交易、商户退款号、退款金额、退款状态和渠道身份。
- 成功和失败均按 APIv2 XML ACK 返回。只有事件与恢复任务在同一事务提交后才返回 `return_code=SUCCESS`；失败返回 `return_code=FAIL`，供微信重试。重复通知必须幂等。

## 强制实现与安全条件

1. 只从受控配置读取 32 字节 APIv2 密钥；不把APIv2密钥写入模板、日志或接口响应。退款请求另外使用微信要求的商户双向证书。
2. 请求/响应使用固定 HTTPS 主机、有限时长与响应大小、禁止重定向/代理继承；XML拒绝DTD、实体声明、重复字段和畸形数据。
3. 支付通知验签后才解析业务事实；退款通知成功解密并严格核对本地关联单据后才可入箱。事件与恢复任务必须同一事务提交，worker复用既有支付/退款领域事实服务。
4. APIv2查单/退款查询响应必须验签；缺签名、未知错误、身份/金额不符或含糊传输结果均不构成付款、退款、关单或不存在事实。
5. 支付通知入箱检查 openid；持久化只保留需要恢复的已核验事实，不保留 openid 或原始 XML。失败响应不泄漏内部错误。
6. 不以预付令牌加密密钥代替商户密钥，也不把 APIv3 RSA私钥、公钥映射或 AES-GCM 通知密钥当作 APIv2 配置。

## 当前门禁状态

APIv2 适配器、XML签名/解析、支付/退款通知路由与配置已切换到 APIv2。**本次转换尚未运行回归测试或完成真实平台联调**；此前基于 APIv3 的T048隔离测试不覆盖当前XML协议，因此G-PROTOCOL 的当前 APIv2 回归仍待补齐。回调、资金出站和worker开关继续默认关闭，生产通知地址仍未登记。G-LIVE、G-DATA、G-UI与G-LIVE-SHIPPING均未因本次代码改动而通过。

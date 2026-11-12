# 快递100物流轨迹接入补充

日期：2026-11-04。用户补充：物流服务已经开通，提供[地图轨迹文档](https://api.kuaidi100.com/document/5ff2c3e7ba1bf00302f5612e)。本补充属于当前商城任务，不新建功能分支。

## 已知事实与首期决定

官方索引将该文档列为地图轨迹查询，与普通实时查询、订阅推送分列。2026-11-06按官方搜索索引重新核对地图API：`POST https://poll.kuaidi100.com/poll/maptrack.do`，表单字段含`customer`、签名和JSON字符串`param`；签名为`MD5(param + key + customer)`并转大写。`param.com`使用小写公司编码，`num`为6–32字符；`from`/`to`为标准行政区格式；`phone`按公司规则可选或必填；`resultv2=5`提供高级状态和区域字段；`needCourierInfo`默认关闭。单票至少间隔30分钟、24小时不超过48次。[官方地图接口](https://api.kuaidi100.com/document/5ff2c3e7ba1bf00302f5612e)、[官方接口索引](https://api.kuaidi100.com/document/apidocumentation)。官方详情页本次仍超时，但搜索索引返回了接口字段和频率说明；已开通服务不等于已提供密钥、额度或授权发送真实用户资料。

按“本地fake闭环/真实provider请求”分层：后端统一适配、缓存和限流，前端按订单权限读轨迹，不直连第三方。fake闭环已实现；真实请求仅在development/test且显式开启live模式与出站开关时调用，production仍保持门禁。2026-11-11用户确认采用地图轨迹（含地址）方式，授权把发货地与收件地的省/市/区县名称作为`from`/`to`发送给快递100；不发送收件人姓名或详细地址。2026-11-11用户另行授权：对快递100明确要求电话核验的承运商（顺丰速运、顺丰快运、中通快递）发送收件人完整电话，仅用于物流核验，不落库、不回传、不写日志，且要求本订单有效履约同意包含`recipient_contact`。同日用户确认地图+预计送达按提供的快递100截图信息层级实现，采用`resultv2=7`并在小程序原生地图绘制预测路线，配色与组件沿用现有商城风格。订阅推送、电子面单、自动寄件/支付运费不因本次链接自动加入范围。

## 服务端设计

- 新增`backend/src/integrations/kuaidi100_client.py`与`mall_logistics_service.py`，使用现有httpx，独立于订单与支付服务。
- 地图查询地址采用官方`https://poll.kuaidi100.com/poll/maptrack.do`，表单customer/sign/param；签名按序列化后的param字符串、key、customer拼接后MD5大写。该签名算法仅遵循供应商协议，不作为项目自身密码或通用安全算法。
- 参数只取可信订单包裹：公司小写编码、运单、标准出发/目的行政区。地图接口要求`from`和`to`；这两项以及部分承运商需要的phone均属买家物流资料，真实出站须先满足G-DATA并限定目的。不能以脱敏电话代替校验值，也不能把完整号码发给前端。
- `resultv2=7`，返回高级状态、区域、预测路线（`predictedRoute`）、预计到达时间及AI时效字段；不发送`needCourierInfo=true`，不采集或返回揽件/派件员姓名和私人电话。map接口的`trailUrl`可能包含令牌，不进入快照、普通响应或日志。服务端所有worker共享单票频控：至少30分钟一次且每天不超过48次。
- 承运商电话规则：仅对顺丰速运(`shunfeng`)、顺丰快运(`shunfengkuaiyun`)、中通快递(`zhongtong`)发送`phone`，值取订单地址快照中的收件人完整电话；发送前校验本订单`consent_record_id`对应的有效履约同意包含`recipient_contact`，否则不发送并等待供应商返回核验失败。电话只进入本次请求体，不写数据库、日志、审计详情或接口响应。
- `KUAIDI100_CUSTOMER`、`KUAIDI100_KEY`、`KUAIDI100_ENABLED`等仅后端环境配置，默认禁真实出站；实际配置名为`KUAIDI100_CUSTOMER`、`KUAIDI100_KEY`、`MALL_KUAIDI100_MODE=fake`及`MALL_KUAIDI100_OUTBOUND_ENABLED=false`。不把key、签名、完整请求、原文电话或地图链接里的私密令牌写日志。

以上协议摘要参照官方地图文档；当前账户适用的电话规则、可用功能及请求编码由接入测试固定，不推测全部快递相同。

## 查询、缓存与恢复

用户从本人订单主动查看物流时，读取本地快照；首次/过期才创建唯一查询任务。默认相同公司+运单查询间隔至少30分钟，所有买家/管理员刷新共用限制，配置不得低于适用服务要求；普通查询单票每日上限按文档及账户约定执行。[实时查询频率说明](https://api.kuaidi100.com/document/5f0ffb5ebc8da837cbd8aefc)

不对所有运单后台高频轮询，不因前端反复打开产生多次计费请求。缓存命中显示更新时间；查询中显示旧快照及更新中；无轨迹、电话校验失败、权限额度不足、服务暂不可用分别呈现，不用“运输中”掩盖错误。

每次查询绑定shipment.id及version和公司/运单身份摘要。更正运单后旧快照失效，旧任务/响应不能覆盖新单；任务领取和查询时间占用用数据库条件更新，避免多worker同票同时查。失败退避且仍遵守单票频率限制，终态数据也不在每次打开重新查。

返回轨迹文本先剔除/脱敏原文手机号、派件员私人联系等非必要信息。地图链接不成为永久公开访问入口，不进普通日志。地图采用小程序原生`map`组件按预测节点经纬度绘制，不使用`web-view`或`trailUrl`；坐标只保留到快照用于本页展示。

## 存储与接口增量

不新增业务表，扩展`mall_shipments`：`logistics_provider=kuaidi100, logistics_status, provider_state, tracking_identity_hash, tracking_snapshot JSON, logistics_fetched_at, logistics_next_query_at, logistics_last_error_code`。snapshot只保留规范化安全节点/行政区、预测节点经纬度、当前城市名和预计到达文本；不存customer/key/sign、完整原始报文、公开永久map URL或收件人电话。

已实现三个本项目接口（不是快递100的对外接口）：

1. `GET /api/v1/mall/orders/{orderId}/logistics`：只允许买家本人，返回快递/运单、缓存状态、规范化节点、更新时间、可选预计信息和是否支持地图；必要查询由唯一任务推进。
2. `GET /api/v1/admin/mall/orders/{orderId}/logistics`：有订单/履约读取范围的后台人员查询相同安全快照。
3. `POST /api/v1/admin/mall/shipments/{shipmentId}/logistics-refresh`：有履约权限、幂等键与版本；排队查询或告知下次允许时间，不绕过供应商限流。

本地发货事实与快递100轨迹分别记录。快递100签收只是一项物流证据，不自动代表用户确认收货、资金解冻、退货验收或绩效重新核算。

## 上线输入与验收

实施时在后端配置所需凭据、账户权益及允许出站目标；用户此刻无需贴密钥。地图页面、订阅能力、签收联动策略不提前承诺，未核实的权限不以“已开通”直接放行。

必须验证：签名及精确param、同单缓存/30分钟限制、多worker及重复刷新、无记录与校验/额度错误、运单更正旧响应、买家越权、日志原文、时间/预计值为空、查询签收不触发其它系统终态。

## 文档获取说明

用户原链接直接抓取一度超时；本次仍未能打开地图详情页，但通过快递100官方文档索引的搜索结果核对了查询端点、字段及频控。实时查询官方文档可直接打开，确认单票至少间隔30分钟、24小时不超过48次以及相关phone规则。未登录其管理后台、未调用账户接口、未查询真实运单。订阅相关文档只作为后续权益核对来源，本期不定义其回调接口。

## 当前实现状态（2026-11-06）

适配器按`maptrack.do`构造签名表单，HTTP层有截止时间、响应字节上限且禁用重定向。service把时间、说明、状态及粗粒度区域规范化，过滤电话号码；不接收/返回`trailUrl`、派件员信息或原始payload。`LogisticsSnapshot.source`区分fake/live/null。本人GET、管理员GET及有权限刷新共用持久查询任务和每票至少30分钟冷却，管理员刷新有包裹版本与持久幂等保护。订单所有权、手机号脱敏、不同错误状态、查询签收不代表收货与旧运单响应栅栏均有本地或隔离MySQL测试。2026-11-11新增地图能力：`resultv2=7`解析`predictedRoute`与`arrivalTime`，快照保存预测节点经纬度、当前城市名和预计到达文本，`mapAvailable`在至少两个有效节点时为true；对顺丰/中通按同意范围发送完整收件电话。小程序物流页在小程序原生`map`绘制路线和当前点，并在页面顶部显示预计送达卡片。

当前worker在development/test且模式fake、出站关闭时调用本地fake客户端；development/test且模式live、出站开启时调用真实adapter，要求发货地与收件地均有完整省/市/区县名称（缺失返回`config_required`），只把这三项行政区名称作为`from`/`to`发送；顺丰/中通在订单履约同意包含`recipient_contact`时附带收件人完整电话。production始终返回安全门禁状态，不调用Kuaidi100 adapter。后台配送设置已新增发货地址省/市/区县名称输入，订单收货地址快照同步保存`regionNames`。虽然adapter通过模拟HTTP校验签名/字段，真实商户密钥、电话校验规则、账号额度/订阅和真实运单均未核验；2026-11-11用户已明确授权地图轨迹方式下发送行政区名称，并授权对电话核验承运商发送完整收件电话，但尚未执行真实查询。fake客户端返回带`source=fake`的合成预测路线，用于本地地图展示与回归；真实地图/预计结果仍待真实运单核验。全局mall worker也默认关闭。

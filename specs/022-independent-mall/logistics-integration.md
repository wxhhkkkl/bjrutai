# 快递100物流轨迹接入补充

日期：2026-11-04。用户补充：物流服务已经开通，提供[地图轨迹文档](https://api.kuaidi100.com/document/5ff2c3e7ba1bf00302f5612e)。本补充属于当前商城任务，不新建功能分支。

## 已知事实与首期决定

官方索引将该文档列为地图轨迹查询，与普通实时查询、订阅推送分列。2026-11-06按官方搜索索引重新核对地图API：`POST https://poll.kuaidi100.com/poll/maptrack.do`，表单字段含`customer`、签名和JSON字符串`param`；签名为`MD5(param + key + customer)`并转大写。`param.com`使用小写公司编码，`num`为6–32字符；`from`/`to`为标准行政区格式；`phone`按公司规则可选或必填；`resultv2=5`提供高级状态和区域字段；`needCourierInfo`默认关闭。单票至少间隔30分钟、24小时不超过48次。[官方地图接口](https://api.kuaidi100.com/document/5ff2c3e7ba1bf00302f5612e)、[官方接口索引](https://api.kuaidi100.com/document/apidocumentation)。官方详情页本次仍超时，但搜索索引返回了接口字段和频率说明；已开通服务不等于已提供密钥、额度或授权发送真实用户资料。

首期按“本地fake闭环/真实provider请求”分层：后端统一适配、缓存和限流，前端按订单权限读轨迹，不直连第三方。fake闭环已实现；真实请求留在G-LIVE/G-DATA门禁内，须确认买家校验资料用途和账户权限后才能接通。普通轨迹是首期功能；地图视图及预计信息按实际能力与本轮UI参考图确定展示。订阅推送、电子面单、自动寄件/支付运费不因本次链接自动加入范围。

## 服务端设计

- 新增`backend/src/integrations/kuaidi100_client.py`与`mall_logistics_service.py`，使用现有httpx，独立于微信发货适配器。
- 地图查询地址采用官方`https://poll.kuaidi100.com/poll/maptrack.do`，表单customer/sign/param；签名按序列化后的param字符串、key、customer拼接后MD5大写。该签名算法仅遵循供应商协议，不作为项目自身密码或通用安全算法。
- 参数只取可信订单包裹：公司小写编码、运单、标准出发/目的行政区。地图接口要求`from`和`to`；这两项以及部分承运商需要的phone均属买家物流资料，真实出站须先满足G-DATA并限定目的。不能以脱敏电话代替校验值，也不能把完整号码发给前端。
- `resultv2=5`为首期上限，提供高级状态及区域信息；不开`resultv2=7`的AI预计路线，不发送`needCourierInfo=true`，不采集或返回揽件/派件员姓名和私人电话。地图返回的`trailUrl`可能包含令牌，只按临时展示策略处理，不进入快照、普通响应或日志。服务端所有worker共享单票频控：至少30分钟一次且每天不超过48次。
- `KUAIDI100_CUSTOMER`、`KUAIDI100_KEY`、`KUAIDI100_ENABLED`等仅后端环境配置，默认禁真实出站；实际配置名为`KUAIDI100_CUSTOMER`、`KUAIDI100_KEY`、`MALL_KUAIDI100_MODE=fake`及`MALL_KUAIDI100_OUTBOUND_ENABLED=false`。不把key、签名、完整请求、原文电话或地图链接里的私密令牌写日志。

以上协议摘要参照官方地图文档；当前账户适用的电话规则、可用功能及请求编码由接入测试固定，不推测全部快递相同。

## 查询、缓存与恢复

用户从本人订单主动查看物流时，读取本地快照；首次/过期才创建唯一查询任务。默认相同公司+运单查询间隔至少30分钟，所有买家/管理员刷新共用限制，配置不得低于适用服务要求；普通查询单票每日上限按文档及账户约定执行。[实时查询频率说明](https://api.kuaidi100.com/document/5f0ffb5ebc8da837cbd8aefc)

不对所有运单后台高频轮询，不因前端反复打开产生多次计费请求。缓存命中显示更新时间；查询中显示旧快照及更新中；无轨迹、电话校验失败、权限额度不足、服务暂不可用分别呈现，不用“运输中”掩盖错误。

每次查询绑定shipment.id及version和公司/运单身份摘要。更正运单后旧快照失效，旧任务/响应不能覆盖新单；任务领取和查询时间占用用数据库条件更新，避免多worker同票同时查。失败退避且仍遵守单票频率限制，终态数据也不在每次打开重新查。

返回轨迹文本先剔除/脱敏原文手机号、派件员私人联系等非必要信息。地图链接不成为永久公开访问入口，不进普通日志；实际展示时还需校验HTTPS目标白名单、小程序业务域名和订单授权。首期没有用户确认的地图视觉，不先做web-view页面或手绘地图。

## 存储与接口增量

不新增业务表，扩展`mall_shipments`：`logistics_provider=kuaidi100, logistics_status, provider_state, tracking_identity_hash, tracking_snapshot JSON, logistics_fetched_at, logistics_next_query_at, logistics_last_error_code`。snapshot只保留规范化安全节点/行政区、可选预计时间；不存customer/key/sign、完整原始报文或公开永久map URL。

已实现三个本项目接口（不是快递100的对外接口）：

1. `GET /api/v1/mall/orders/{orderId}/logistics`：只允许买家本人，返回快递/运单、缓存状态、规范化节点、更新时间、可选预计信息和是否支持地图；必要查询由唯一任务推进。
2. `GET /api/v1/admin/mall/orders/{orderId}/logistics`：有订单/履约读取范围的后台人员查询相同安全快照。
3. `POST /api/v1/admin/mall/shipments/{shipmentId}/logistics-refresh`：有履约权限、幂等键与版本；排队查询或告知下次允许时间，不绕过供应商限流。

微信发货信息上传与平台确认继续独立执行。快递100签收只是一项物流证据，不自动代表用户确认收货、微信平台确认、资金解冻、退货验收或绩效重新核算。

## 上线输入与验收

实施时在后端配置所需凭据、账户权益及允许出站目标；用户此刻无需贴密钥。地图页面、订阅能力、签收联动策略不提前承诺，未核实的权限不以“已开通”直接放行。

必须验证：签名及精确param、同单缓存/30分钟限制、多worker及重复刷新、无记录与校验/额度错误、运单更正旧响应、买家越权、日志原文、时间/预计值为空、查询签收不触发其它系统终态，以及微信同步失败不影响快递100轨迹读取。

## 文档获取说明

用户原链接直接抓取一度超时；本次仍未能打开地图详情页，但通过快递100官方文档索引的搜索结果核对了查询端点、字段及频控。实时查询官方文档可直接打开，确认单票至少间隔30分钟、24小时不超过48次以及相关phone规则。未登录其管理后台、未调用账户接口、未查询真实运单。订阅相关文档只作为后续权益核对来源，本期不定义其回调接口。

## 当前实现状态（2026-11-06）

适配器按`maptrack.do`构造签名表单，HTTP层有截止时间、响应字节上限且禁用重定向。service把时间、说明、状态及粗粒度区域规范化，过滤电话号码；不接收/返回`trailUrl`、经纬度或派件员信息。`LogisticsSnapshot.source`区分fake/live/null。本人GET、管理员GET及有权限刷新共用持久查询任务和每票至少30分钟冷却，管理员刷新有包裹版本与持久幂等保护。订单所有权、手机号脱敏、不同错误状态、查询签收不代表收货与旧运单响应栅栏均有本地或隔离MySQL测试。

当前worker仅在development/test且模式fake、出站关闭时调用本地fake客户端；production或live模式始终返回安全门禁状态，不调用Kuaidi100 adapter。虽然adapter通过模拟HTTP校验签名/字段，真实商户密钥、电话校验规则、账号额度/订阅和真实运单均未核验；G-DATA已批准的仅是商城内部单对象查看，真实provider请求中的买家原文传输未获授权且保持关闭。地图标记目前固定false；不表示地图/预计到达视觉已完成。全局mall worker也默认关闭。

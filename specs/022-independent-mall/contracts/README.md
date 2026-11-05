# 接口契约：自营独立商城

日期：2026-11-04。机器可读定义：[openapi.json](openapi.json)，浏览索引：[operation-index.md](operation-index.md)。全部为拟实现契约，不代表当前已有路由。用户业务接口统一`/api/v1/mall`，后台`/api/v1/admin/mall`，绩效调整沿用`/api/v1/admin/performance`，渠道通知独立。

JSON为OpenAPI 3.1，定义请求、响应、路径参数、金额、状态、权限、幂等键及需求引用。本文补充跨字段、事务和兼容语义；两者冲突须修正契约，不凭客户端猜。

## 1. 共通协议

- 业务成功响应为`{code:0,message,data,requestId,serverTime}`，时间RFC3339。ID为十进制字符串，金额整数分，不用浮点元。POST默认返回200或异步202，不以HTTP202表示资金已成功。
- 错误按实际HTTP 400/401/403/404/409/422/503返回Error包；不存在和越权对象对普通买家统一404，不泄露他人记录是否存在。
- JWT只证明会话，所有动作及幂等重放重新核验数据库账号active、当前角色和对象范围。后台同时有admin身份和权限；普通买家不要求顾问角色。
- 除纯报价POST外，写操作必须`Idempotency-Key`，16–128字符，同actor/action/key+同payload返回原记录；异payload409。命令body规范化后摘要，不存明文手机号/地址或完整票据响应到缓存。
- `expectedVersion`指被操作聚合当前version；子资源审核/发货/归属要求对应父或源版本，成功版本加一，过期409并返回新版本及冲突类型，不自动覆盖。
- GET不直接产生退款/支付；本地未知结果可触发唯一查证工作项，重复刷新不增加渠道副作用。查询外部结果的POST是异步核查，不等于手工改事实。
- 列表默认20、最大100，稳定排序；cursor由服务端签名或校验，含筛选摘要与排序位置，不携带完整隐私。消费来源混合明细按时间/来源/ID全局排序，不各取一页拼接。
- 报价5分钟有效，quoteToken绑定用户、商品数量/版本、地址/规则版本及金额，包含引用与摘要而非原始隐私。提交仍校验所有版本与库存；过期或变价返回冲突，要求重新报价，无库存占用。
- 商品图片可公开，售后/发票/对账/导出文件私有；短时URL不进日志、分析或幂等响应持久缓存。文件与导出就绪时可重领新URL，不重复开票或生成业务。

### 错误编码（本功能预留）

| HTTP / code | 名称 | 行为 |
|---|---|---|
| 401 / 40160 | 会话不可用 | 重新登录，保留安全选购意图 |
| 403 / 40360 | 权限或规范门禁未满足 | 不执行，后台显示缺少具体能力而非重试退款 |
| 404 / 40460 | 对象不可访问 | 不泄露其他买家记录 |
| 409 / 40960 | VERSION_CHANGED | 返回currentVersion，用户核对后再提交 |
| 409 / 40961 | STOCK_OR_QUOTE_CHANGED | 重取报价，不静默改额 |
| 409 / 40962 | STATE_NOT_ALLOWED | 保留原事实，例如退款中不能撤回 |
| 409 / 40963 | IDEMPOTENCY_PAYLOAD_MISMATCH | 使用同一意图原内容查结果；新意图用新key |
| 409 / 40964 | PERFORMANCE_INPUT_STALE | 先重算或补证，不审核旧估算 |
| 409 / 40965 | REFUND_CAPACITY_RESERVED | 等待原申请终态，不能超退 |
| 409 / 40966 | INVOICE_RESULT_REQUIRES_RECONCILIATION | 核实是否实际出票，不再次开具 |
| 422 / 42260 | INVALID_BUSINESS_INPUT | 字段/跨字段规则不满足，保留输入 |
| 503 / 50360 | DEPENDENCY_UNAVAILABLE | 支付/文件/平台条件不足；未知仍按原请求查询，不换号退钱 |

## 2. 数据与跨字段校验

### 商品、库存与配置

`ProductWrite`可保存不完整草稿，发布时要求有效分类、主图、描述、正价SKU及已配置配送；不接受品牌/公共属性/评价字段。SKU初始库存仅新SKU创建使用，已有SKU必须走库存调整命令，不能更新商品直接改可售量。分类更新使用`CategoryPatch.expectedVersion`；停用关联在售商品须先迁移或下架。

SettingsUpdate的dispatchAddress/returnAddress为仓库专用配置写入，不引用普通买家地址簿。GET只返回脱敏配置。公开给售后用户的退货指引使用经营方明确用于退货服务的业务地址和联系信息，不复用其他用户收件资料；完整个人联系电话交付仍受规范门禁约束。

`SettingsUpdate.expectedVersion`与settings.version必须一致，前者为乐观锁；启用购买时检查主体、商户、商品、退货、平台及规范条件，不能仅把布尔值改true。

### 地址与订单

AddressWrite包含买家主动提交原文，响应仅Address脱敏字段。AddressPatch省略phone/addressLine时保留原文，提交新值则替换；不允许“取原电话”通用GET。地址修改不改变历史订单快照。订单换地址仅发货前、无相冲售后、配送允许且运费不增加时可办，其他退回原交易重建路径按实际状态处理。

Quote返回可信明细与总额。OrderCreate只提交quoteToken及备注/告知版本，不能提交自定价格和客户归属。发货、售后、关单按同一订单锁串行判定；同刻只允许一个有效支付请求。

### 售后与退款

AftersaleCreate默认scope=goods，items至少一项；scope=freight_only时items为空且method=refund_only，仅请求原单剩余可退运费，不能借此申请商品补偿或任意转款。默认商品退款按所选数量的成交单价，客户端没有任填退款金额入口。

同一原明细仅一个有效处理中申请，首个完成/拒绝后才可对剩余合法数量重提。金额占用沿申请→审核→资金执行传递，审核请求中的freightRefundCent只可在原剩余可退运费内，变更需理由。

ReturnReceipt.sellableItems按售后明细ID验证数量与累计实物验收，不因财务退款再次回库；partially_accepted/disputed生成待核实，不由一次验收擅自更改获准退款金额。仅退款无实物不回库存。

Execute-refund仅待执行退款可用，202表示准备/处理中。retry必须先核实原请求且复用原outRefundNo；已关闭确需另建请求在服务内部串联前驱并重新核额度，用户不可任填渠道单号。

### 发票与文件

company要求taxNo，personal不强制。普通开票详情只给taxNoMasked；财务实际开具所需完整资料仅经`billing-release`目的限定动作获得，该动作与fulfillment-release一样在规范提案未落实前关闭，不放进普通GET。

财务record时金额/主体/原申请版本核对；真实已出但本地版本变化转待核实保存事实，不丢票、不自动再开。replacementForId只在原蓝票已按实际规则释放对应有效覆盖后允许，仍关联原申请及红票；同票号重复返回原记录，异事实冲突。

red-pending登记待处理原因，不代表税务红冲成功；确切等待对方确认状态通过财务处理记录留证。red-record是实际红票回传，须关联原蓝票、核有效剩余覆盖及真实PDF。文件丢失补交同票，不再开票；具体补交通过发票记录同身份更新票据文件的受控服务路径处理，version和审计不可省。

文件token只允许actor对应purpose：买家aftersale_proof；后台product_image需商品权、invoice_pdf需开票权、reconciliation_evidence需对账权。`mall.files.read/write`不是独立全文件特权，必须同时满足用途权限及对象归属。票据PDF≤10MB、图片JPG/PNG≤5MB；verify核HEAD、MIME和checksum，生产缺COS凭据不可降级放行。

FinanceExport必须显式from/to/format，范围及权限写入命令；不能默默扩大或截断。异步完成后的entityId关联私有导出文件，获取时重验原资金导出权限（不仅files.read），无永久链接。导出文件MIME仅受控生成XLSX/CSV，用户不能通过上传ticket伪造该用途。

## 3. 权限与条件性动作

权限按操作索引配置到后台权限常量与种子，实时检查数据库当前授权。`mall.products.*`、`mall.stock.*`、`mall.orders.*`、`mall.shipments.write`、`mall.aftersales.*`、`mall.returns.receive`、`mall.payments.*`、`mall.refunds.*`、`mall.invoices.*`、`mall.settings.*`、`mall.reconciliations.*`、`mall.finance.export`等可组合，不默认授予普通组织管理员。

`fulfillment-release`与`billing-release`是条件性契约，不代表已新增安全访问权限：

- 必须先落地[规范提案](../governance-proposal.md)及告知版本、目的和最小权限。
- 领取前查指定订单或开票任务状态与本人责任权限；不能接受任意用户ID查询。
- 返回禁止缓存、120秒短时使用提示，记录auditId；客户端短时清除只是辅助，不能声称已消除截图/复制风险。
- 同幂等意图重复不存原文响应副本，再取时重验条件；门禁关闭始终40360。
- 不能仅用“管理员已登录”或一般files.read放行。

普通订单、地址和发票GET脱敏。买家主动提交的输入只用于相应目的，完整值不得进入request日志或错误回显。

## 4. 渠道通知与外部适配契约

`/api/v1/mall-gateway/wechat/payment-notify`与`refund-notify`以下均为受G-PROTOCOL约束的目标协议，与现宪章II尚有冲突，见[独立草案](../protocol-governance-proposal.md)。正式采纳前不得实现/部署两个端点，不以普通业务包装占位接收通知。目标端点不使用用户JWT和业务envelope；头部验签、时间窗口及重放检查、公钥/证书轮换、解密、交易主体币种金额匹配后，将event和唯一处理任务显式提交，再204。失败应答按实施前核验的外部协议；重复事件不重复业务作用。其它业务API仍遵守统一响应。

支付出站参数只由订单价款和受控配置生成；退款只使用原支付及获准额度，禁止客户端指定mchid/appid/outRefundNo。httpx设置连接及读取超时，未知落状态并查原请求，不盲目重试创建。

微信发货服务在当前账号适用且官方字段核对后接入。计划只定义本地适配器输入order/transaction、package、courier、tracking和版本；具体微信字段按接入当时官方文档建立映射及契约测试，不把本JSON当微信平台接口规范。平台同步失败不重复发货，平台确认与本地收货分开。

## 5. 既有接口兼容扩展（不误称新增路由）

| 当前入口 | 必须修改的行为 | 兼容要求 |
|---|---|---|
| `/api/v1/contributions`及overview/trend/detail | 合并商城来源、统一筛选及可追溯明细 | 既有Bill详情保留；新增sourceType/sourceRecordId用于商城定位，旧数字billId不得误解为商城ID |
| `/api/v1/admin/contributions/dashboard`、组织/人员排行、报表 | 汇总、latest30及导出包含商城 | 原字段含义不变，sourceBreakdown与净收分列，不把组织管理基数重复加总 |
| `/api/v1/admin/performance/settleable-periods` | 并入商城有数据月及只有已审核调整可处理月份 | 不因提前创建协调行使月份错误排除 |
| `/api/v1/admin/performance/estimates`及settlements流程 | 统一来源、核算版本、冻结输入、已确认调整 | 已冻结取正式结果；review输入变化40964；旧无商城样本数值不变 |
| `/api/v1/my/performance/commission`、`/org/performance/commission`及组织绩效 | 个人和组织已确认历史都取冻结，不用实时值冒充 | 新增净可兑现字段，原commissionCent仍正常绩效 |
| `/api/v1/admin/performance/settlements/{period}/points/{distributor_id}/{rule_type}/redeem` | 同事务锁结果/调整应用，按净额核销，不绕过债权 | 原路径、权限performance.settle保留；无调整时结果不变；已核销旧行不回写 |

新增统一来源明细字段：sourceType、sourceRecordId、customerId nullable、distributorId nullable、attributedOrgId、occurredAt、businessPeriod、originalAmountCent、refundAmountCent、performanceBaseCent、sourceVersion。原字段Bill-only含义不能突然变成商城订单号；客户端通过sourceType路由。

绩效新增字段：normalCommissionCent、confirmedAdjustmentCent（带符号）、appliedDebtCent、redeemableCent、pendingDebtCent、evidenceStatus、sourceBreakdown。期内普通绩效与差额分开，组织内/管理两种基数不能相加伪称消费。新增净可兑现查询只是便于核销核实，不新增钱包。

## 6. 例子

**同键异body**：订单创建keyK首次成功关联订单123；再次keyK但换quoteToken返回40963，不创建第二单；同内容重试且仍本人则返回123最新脱敏事实。

**未知退款**：refund456原outRefundNo稳定，提交后网络超时显示unknown；query查得PROCESSING继续占用；查得SUCCESS只累计一次成功退款；invoice待红冲和绩效差额分别排队。

**冻结后退款**：正常880/220冻结，退完商城商品后模拟400/160；生成−480/−60，不改原值；后期正常100、已分配债480，redeemable0、结余380，核销接口不能再兑出100。

## 7. 契约验收

静态检查OpenAPI引用、operationId、路径参数、所有写操作幂等/乐观版本、公开/网关安全例外及需求编号。随后按主验收AC及规划故障场景编写失败契约测试，不通过真实MySQL并发和资金恢复测试不开放购买。当前文件中的104个操作（含物流补充3个）包含细分查询/动作，不代表页面数量；不得据此扩展营销或未请求模块。

### 最后校正

工作台采用`dynamic_any_mall_permission`身份策略：有任一有效商城办理/读取权限可进入，只返回该角色能处理的待办与金额，不要求财务先取得全部订单读取权。异步命令使用`dynamic_original_action_permission`，每次按原动作权限和对象范围校验。两者是`x-permission-policy`策略名，不是要加入角色种子的万能权限。

Order响应提供invoiceRequestId、aftersaleIds和paymentId，支持从原单进入正在办理的记录；未创建时为空，不能让用户只看到状态却找不到待补充申请。Aftersale包含明细ID、数量、凭证及审核理由以便真实验收。

票据totalCent均用正的金额绝对值，蓝红方向由kind区分，红票数值在税务原始文件中仍按实际出具内容核验；记录接口不接受0金额伪票。源消费可附orderId，是否提供及能否进入订单仍依实际买家/后台权限，推广人员不能因看到自己的业绩来源获得订单全量资料。

## 8. 快递100物流补充（0.2.0）

用户已开通快递100；首期按[物流补充](../logistics-integration.md)接入轨迹查询。新增`getMyMallLogistics`、`getAdminMallLogistics`及`refreshMallLogistics`；该次0.2.0基线为92路径、104操作、136个schema，分析修订后的当前数量见下一节。供应商密钥、签名、原文电话和任意运单查询参数不进入本项目客户端契约。

买家及后台读取同一安全快照，GET最多安排唯一查询任务；后台刷新同样遵守同票至少30分钟的共享频率限制，不赋予绕过权。返回缓存状态、更新时间、下次可查时间、规范化节点及可选预计信息；失败与旧轨迹分别表达。快照更新不递增业务包裹version，以免只看物流造成发货纠错冲突；业务运单变更递增version并切换身份摘要，旧响应不得覆盖新单。

地图仅返回是否具备能力，不下发永久公开地图地址。真实地图展示与安全访问方式待G-UI参考图及当前账户/小程序域名核验后确定；这三个接口不承诺地图页面已经可用。订阅回调、电子面单及自动寄件不在本期契约。物流签收不代替本地/微信平台确认、资金状态、退货验收或绩效事实。

## 9. 分析修订（0.3.0）

当前92路径、104操作、142个schema；没有增加业务接口。`getMyMallOrder`返回`ResponseBuyerOrderDetail`，`getAdminMallOrder`返回`ResponseAdminOrderDetail`。原`Order`继续作列表/普通操作摘要，并增加必需`payableAmountCent`；前端不从商品价自行推算可信应付。

两种详情均明确关键时间及空值、买家备注、关闭原因、关联ID、角色可见时间线和`availableActions`。发货时间来自shipment.shippedAt；未发货shipment=null。后台额外返回最小买家身份及internalNote；买家schema禁止internalNote，业务时间线按观看者过滤，不直接输出原始AuditLog.detail。无权的动作不返回，执行时仍重验权限；服务端脱敏适用于所有文本和时间线。

调整响应增加必需`originEvidenceId`与`originResultPresence`，原`originResultId`必需但允许null。原期未命中阶梯时，按冻结证据锚点和原资格/规则重放C0=0，不补写原冻结结果。调整幂等及累计确认以evidence_id为身份；没有可靠历史规则/资格时manual_required，不将当前规则当历史。后期兑现仍沿原净额链路，不引入钱包。

两个通知operation显式标记`x-implementation-gate: G-PROTOCOL`，此元数据仅用于阻止越级实施，不是已获规范例外。G-LIVE-SHIPPING由T054先核验官方字段并留映射，T056消费该记录，T131再核验真实账户，不把协议预核验当真实发货成功。

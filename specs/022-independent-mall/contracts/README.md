# 接口契约：自营独立商城

日期：2026-11-04起滚动更新。机器可读定义：[openapi.json](openapi.json)，浏览索引：[operation-index.md](operation-index.md)。契约覆盖完整规划接口，当前已实现子集与阶段边界见本页末尾。用户业务接口统一`/api/v1/mall`，后台`/api/v1/admin/mall`，绩效调整沿用`/api/v1/admin/performance`，渠道通知独立。

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

商品读取的`sort/coverFileId/galleryFileIds`以及SKU的`reservedQuantity/warningQuantity`仅在后台投影返回，支持完整编辑回填；公开读取省略这些字段，仍只展示已上架且分类有效的商品。编辑既有SKU不发送initialStock。客户端价格以十进制字符串转换为整数分，不在界面重算业务价格。

SettingsUpdate的dispatchAddress/returnAddress为仓库专用配置写入，不引用普通买家地址簿。`mall.settings.read`读取仍显示配置状态；同时具备`mall.settings.write`时，GET和保存响应返回已存联系人、电话、地区与完整地址，用于后台核对和修改回显。公开给售后用户的退货指引使用经营方明确用于退货服务的业务地址和联系信息，不复用其他用户收件资料；完整个人联系电话交付仍受规范门禁约束。

`SettingsUpdate.expectedVersion`与settings.version必须一致，前者为乐观锁；启用购买时检查主体、商户、商品、退货、平台及规范条件，不能仅把布尔值改true。

### 地址与订单

AddressWrite包含买家主动提交原文，响应仅Address脱敏字段。AddressPatch省略phone/addressLine时保留原文，提交新值则替换；不允许“取原电话”通用GET。地址修改不改变历史订单快照。订单换地址仅发货前、无相冲售后、配送允许且运费不增加时可办，其他退回原交易重建路径按实际状态处理。

当前地址/购物车/报价切片：地址省市区代码各6位数字；编辑不接受显式null或脱敏电话。新地址必须同时提交`consentVersion`和`consentConfirmed:true`，服务端核对版本后新建mall_address用途证据；仅传版本号不构成确认，也不复用旧注册记录。地址编辑沿用其既有收件用途，不重录原值到证据scope。购物车加购按本人/SKU合并数量，上限999，不占库存；数量大于当前可售量会明确失效，不自动减少用户选择。报价5分钟令牌仅含买家、地址引用、选购项和校验摘要，不含原文资料；数据库当前读复核，避免沿用认证事务的旧快照。地址/报价阶段不修改库存，不能把单独报价复核当成完整下单事务；订单实现见下段。

订单切片补充：`OrderCreate`必须携带当前告知版本及`consentConfirmed:true`；该确认对应支付和履约两个purpose版本，订单/付款处理、收件与物流scope分别留证。createMallOrder已在短事务中按SKU ID升序直接取得独占锁，再复核报价并保存订单、商品/地址/规则快照、用途证据、库存占用流水、到期查证任务及命令结果；不先取共享SKU锁再升级。不同内容同键409；原成功意图重放不再次占用，也不因原报价过期或商城暂停新购买而新建订单。本人订单列表继续只读脱敏摘要；本人订单详情在重新核验订单归属后返回该订单快照中的完整收件电话和地址，不向其他买家、列表摘要或后台普通详情扩散；商户/预付信息及内部备注仍省略。缺少active指针时仍展示实际最近付款尝试的unknown等状态，不能误报从未发起付款。支付/履约动作未实现时availableActions为空，不提供虚假的付款按钮。

未创建任何付款请求历史的订单可由内部服务关闭并唯一释放；存在任何付款历史，包括pointer丢失、unknown/failed/closed，均拒绝此本地直关路径，须交给后续T046渠道查证。取消API、可用收银台及到期任务handler尚未注册；单纯本地超时不会触发释放。到期任务已持久排程不等于自动关单已运行。

Quote返回可信明细与总额。OrderCreate只提交quoteToken及备注/告知版本，不能提交自定价格和客户归属。发货、售后、关单按同一订单锁串行判定；同刻只允许一个有效支付请求。

### 售后与退款

AftersaleCreate默认scope=goods，items至少一项；scope=freight_only时items为空且method=refund_only，仅请求原单剩余可退运费，不能借此申请商品补偿或任意转款。默认商品退款按所选数量的成交单价，客户端没有任填退款金额入口。

同一原明细仅一个有效处理中申请，首个完成/拒绝后才可对剩余合法数量重提。金额占用沿申请→审核→资金执行传递，审核请求中的freightRefundCent只可在原剩余可退运费内，变更需理由。

ReturnReceipt.sellableItems按售后明细ID验证数量与累计实物验收，不因财务退款再次回库；partially_accepted/disputed生成待核实，不由一次验收擅自更改获准退款金额。仅退款无实物不回库存。

Execute-refund仅待执行退款可用，202表示准备/处理中。retry必须先核实原请求且复用原outRefundNo；已关闭确需另建请求在服务内部串联前驱并重新核额度，用户不可任填渠道单号。

### 发票与文件

company要求taxNo，personal不强制。普通开票详情只给taxNoMasked；财务实际开具所需完整资料仅经`billing-release`目的限定动作获得。后台要求补充时填写的说明以`infoRequestReason`返回买家，买家重新提交资料后清空。内部单对象范围已按宪章4.0.0批准并实现；运行开关、留存制度引用或告知审阅版本未满足时仍拒绝，不放进普通GET。

`InvoiceCreate`及`InvoicePatch`必须带当前用途告知版本与显式确认；开票申请保存最近一次用途凭证引用，补资料创建新的ConsentRecord并保留旧证据。版本证据仅描述scope，不复制税号、抬头或邮箱。收件/支付/履约/发票用途文案版本与用户协议/隐私政策分开维护；当前仍待业务/法务审阅。该确认只记录对应资料处理用途，不代表接受通用法律协议；宪章4.0.0已批准的内部单对象访问仍需运行配置，不授权第三方原文交付。

首期用户路径为申请→后台人工开具并上传→用户在申请详情下载；不自动对接税务平台或发送邮件。当前小程序不收集邮箱，API中的可选`email`仅保留为兼容字段并标记deprecated；后台不向用户或第三方暴露该字段。用途告知文案从v1更新为v2，旧申请的邮箱列仅按历史资料保留要求处理。

财务record时金额取申请记录、校验原申请版本并绑定已核验PDF；普通后台流程不再手填票号、开具时间和销售主体，三项可在兼容接口中同时提供或全部省略。真实已出但本地版本变化转待核实保存文件事实，不丢票、不自动再开。replacementForId只在原蓝票已按实际规则释放对应有效覆盖后允许，仍关联原申请及红票；提供票号时仍校验重复关联。

red-pending登记待处理原因，不代表税务红冲成功；确切等待对方确认状态通过财务处理记录留证。red-record是实际红票回传，须关联原蓝票、核有效剩余覆盖及真实PDF。文件丢失补交同票，不再开票；具体补交通过发票记录同身份更新票据文件的受控服务路径处理，version和审计不可省。

文件token只允许actor对应purpose：买家aftersale_proof；后台product_image需商品权、invoice_pdf需开票权、reconciliation_evidence需对账权，attribution_evidence需`mall.attribution.write`，performance_adjustment_evidence需`performance.settle`。对账证据接受CSV/XLSX/PDF/JPG/PNG且≤10MB；归属和绩效补证凭证限JPG/PNG/PDF且≤10MB；单条绩效差额最多关联5份补证。`mall.files.read/write`不是独立全文件特权，必须同时满足用途权限及对象归属。绩效补证ID与调整同记录保存；只能查看已绑定文件，不返回永久URL。票据PDF≤10MB、售后图片JPG/PNG≤5MB；verify核HEAD、MIME和checksum，生产缺COS凭据不可降级放行。

客户端上传只允许临时对象；verify在锁定文件状态后按源ETag条件复制到服务端生成的独立私有对象，再核验目标实际字节的大小、类型和SHA256。仅成功后更新数据库对象引用并使其立即可用；旧上传URL不能写入新引用，已核验前缀不得签发客户端PUT凭证。转存失败不进入verified状态。COS返回200仍须核验复制结果XML，不能把内嵌Error当成功。此能力只有替身契约及单元验证，真实COS配置与联调仍关闭。

FinanceExport必须显式from/to/format，时间须包含时区并规范为UTC半开区间`[from,to)`，最多31天，超限明确拒绝，不默默扩大或截断。成功收/退款按各自confirmedAt落范围；处理中、未知等非成功行以记录createdAt落范围展示，但不计为成功金额。幂等命令只保存范围摘要；独立导出请求表保存生成所需的有限筛选、操作者和状态。异步完成后的entityId关联私有导出文件，获取时重验当前`mall.finance.export`与`mall.files.read`（不仅files.read），签发60秒链接且不缓存，无永久链接。导出文件MIME仅受控生成XLSX/CSV，用户不能通过上传ticket伪造该用途；失败只保留安全错误码。当前账务表无渠道费用/结算金额来源，不输出估算值或利润字段。

## 3. 权限与条件性动作

权限按操作索引配置到后台权限常量与种子，实时检查数据库当前授权。`mall.products.*`、`mall.stock.*`、`mall.orders.*`、`mall.shipments.write`、`mall.aftersales.*`、`mall.returns.receive`、`mall.payments.*`、`mall.refunds.*`、`mall.invoices.*`、`mall.settings.*`、`mall.reconciliations.*`、`mall.finance.export`等可组合，不默认授予普通组织管理员。

`fulfillment-release`与`billing-release`是已批准但受运行配置约束的单对象契约：

- 内部范围及最小权限已落地[宪章4.0.0](../../../.specify/memory/constitution.md)；生产开启还要求配置现有留存制度引用和经审阅告知版本。
- 领取前查指定订单或开票任务状态与本人责任权限；不能接受任意用户ID查询。
- 返回`no-store`响应、60秒到期时间和`auditId`；页面需按时清除原文，客户端清除不能消除截图/复制风险。
- 同一幂等键不会缓存或重放原文响应；再次请求时重验当前条件。默认关闭或运行配置不全时记录元数据审计并返回403。
- 不能仅用“管理员已登录”或一般files.read放行。

普通订单、地址和发票GET脱敏。买家主动提交的输入只用于相应目的，完整值不得进入request日志或错误回显。

## 4. 渠道通知与外部适配契约

`/api/v1/mall-gateway/wechat/payment-notify`与`refund-notify`是宪章3.0.0限定的唯一外部响应例外，见[已采纳协议记录](../protocol-governance-proposal.md)。成功ACK为HTTP 204空响应，失败为4xx/5xx及`FAIL`错误体；签名/时间校验、解密和本地交易主体/金额匹配后，将加密resource事件及唯一恢复任务显式提交，再返回204。实现必须幂等、拒绝同事件ID异内容并先提交后ACK；业务worker沿用支付/退款领域服务。端点不使用用户JWT或业务envelope，其他业务API继续使用统一响应。T048本地实现与隔离回归已完成；生产通知注册/部署仍受G-LIVE和具体授权约束。

支付出站参数只由订单价款和受控配置生成；退款只使用原支付及获准额度，禁止客户端指定mchid/appid/outRefundNo。httpx设置连接及读取超时，未知落状态并查原请求，不盲目重试创建。

本项目没有微信平台发货环节，也不接微信发货API。员工在商城后台登记本地包裹与运单即完成发货；快递100轨迹和买家收货确认与本地发货分别记录。

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

绩效新增字段：normalCommissionCent、confirmedAdjustmentCent（带符号）、appliedDebtCent、redeemableCent、pendingDebtCent、evidenceStatus、sourceBreakdown。期内普通绩效与差额分开，组织内/管理两种基数不能相加伪称消费。新增净可兑现查询只是便于核销核实，不新增钱包。待审核/待人工核实调整不进入净可兑现；审批前重锁原期证据并复核累计已确认差额，发现并行审核导致delta过期时返回冲突，需补证重算。

## 6. 例子

**同键异body**：订单创建keyK首次成功关联订单123；再次keyK但换quoteToken返回40963，不创建第二单；同内容重试且仍本人则返回123最新脱敏事实。

**未知退款**：refund456原outRefundNo稳定，提交后网络超时显示unknown；query查得PROCESSING继续占用；查得SUCCESS只累计一次成功退款；invoice待红冲和绩效差额分别排队。

**冻结后退款**：正常880/220冻结，退完商城商品后模拟400/160；生成−480/−60，不改原值；后期正常100、已分配债480，redeemable0、结余380，核销接口不能再兑出100。

## 7. 契约验收

静态检查OpenAPI引用、operationId、路径参数、所有写操作幂等/乐观版本、公开/网关安全例外及需求编号。随后按主验收AC及规划故障场景编写失败契约测试，不通过真实MySQL并发和资金恢复测试不开放购买。当前文件中的104个操作（含物流补充3个及结算安全配置读取）包含细分查询/动作，不代表页面数量；不得据此扩展营销或未请求模块。

### 最后校正

工作台采用`dynamic_any_mall_permission`身份策略：有任一有效商城办理/读取权限可进入，只返回该角色能处理的待办与金额，不要求财务先取得全部订单读取权。异步命令使用`dynamic_original_action_permission`，每次按原动作权限和对象范围校验。两者是`x-permission-policy`策略名，不是要加入角色种子的万能权限。

Order响应提供invoiceRequestId、aftersaleIds和paymentId，支持从原单进入正在办理的记录；未创建时为空，不能让用户只看到状态却找不到待补充申请。Aftersale包含明细ID、数量、凭证及审核理由以便真实验收。

票据totalCent均用正的金额绝对值，蓝红方向由kind区分；工作人员登记并上传后视为其确认所提交票据有效，商城不连接税务平台验真。系统仍校验票据记录与订单/申请金额及红蓝关联规则，不接受0金额记录。源消费可附orderId，是否提供及能否进入订单仍依实际买家/后台权限，推广人员不能因看到自己的业绩来源获得订单全量资料。

## 8. 快递100物流补充（0.2.0）

用户已开通快递100；首期按[物流补充](../logistics-integration.md)接入轨迹查询。新增`getMyMallLogistics`、`getAdminMallLogistics`及`refreshMallLogistics`；该次0.2.0基线为92路径、104操作、136个schema，分析修订后的当前数量见下一节。供应商密钥、签名、原文电话和任意运单查询参数不进入本项目客户端契约。

买家及后台读取同一安全快照，GET最多安排唯一查询任务；后台刷新同样遵守同票至少30分钟的共享频率限制，不赋予绕过权。返回缓存状态、更新时间、下次可查时间、规范化节点及可选预计信息；失败与旧轨迹分别表达。快照更新不递增业务包裹version，以免只看物流造成发货纠错冲突；业务运单变更递增version并切换身份摘要，旧响应不得覆盖新单。

地图按2026-11-11确认的截图信息层级在现有小程序物流页原生实现：`LogisticsSnapshot`增加可选`route`（当前城市名与预测节点经纬度）和`estimatedArrivalText`，`mapAvailable`在预测路线至少两个有效节点时为true。不下发`trailUrl`、地图令牌、派件员资料或供应商原始payload，坐标只用于本页地图绘制，不构成可长期公开的地图入口。订阅回调、电子面单及自动寄件不在本期契约。物流签收不代替买家确认收货、资金状态、退货验收或绩效事实。

## 9. 分析修订（0.3.0）

0.3.0基线为92路径、104操作、142个schema；没有增加业务接口。当前后台发货前检查的0.4.0补充见下一节。`getMyMallOrder`返回`ResponseBuyerOrderDetail`，`getAdminMallOrder`返回`ResponseAdminOrderDetail`。原`Order`继续作列表/普通操作摘要，并增加必需`payableAmountCent`；前端不从商品价自行推算可信应付。

两种详情均明确关键时间及空值、买家备注、关闭原因、关联ID、角色可见时间线和`availableActions`。发货时间来自shipment.shippedAt；未发货shipment=null。后台额外返回最小买家身份及internalNote；买家schema禁止internalNote，业务时间线按观看者过滤，不直接输出原始AuditLog.detail。无权的动作不返回，执行时仍重验权限；服务端脱敏适用于所有文本和时间线。

调整响应增加必需`originEvidenceId`与`originResultPresence`，原`originResultId`必需但允许null，并返回补证文件ID及说明。原期未命中阶梯时，按冻结证据锚点和原资格/规则重放C0=0，不补写原冻结结果。调整幂等及累计确认以evidence_id为身份；没有可靠历史规则/资格时manual_required，不将当前规则当历史。只有原期证据完整的proposed差额可审核；manual_required补证后仍待核实，不会仅因上传附件转为可审核。后期兑现仍沿原净额链路，不引入钱包。

两个通知operation显式标记x-implementation-gate: G-PROTOCOL，该门禁的治理采纳与官方协议核验已完成；此标记用于维持范围追踪，T048本地实现与隔离回归已验收，但不表示真实平台已开通。本项目没有微信平台发货环节，发货只登记商城本地事实，T054/T056原方案已作废。

## 支付核实基础切片（2026-11-06）

已注册prepareMallPayment/getMallPayment两个本人接口。准备请求只接受expectedVersion，同次重放或原活动请求复用同一商户付款身份。恢复续作已接密文预付交付、查原号及关单worker：仅有效待付状态、未申请关闭、未过期、令牌可解密且运行时配置可用时，POST返回canInvoke=true及本次新签名；默认关闭配置下仍为false/null。GET不发调起参数、不触发外部请求或新增任务，并强制刷新查询实体以读取最新核实状态。已核实交易通过内部类型及主体/金额/付款人复核后，才在同一事务转换库存、保存实收及独立消费来源；来源不是已完成US5绩效汇总。支付/退款通知端点已由T048完成本地实现与隔离回归；生产登记仍受G-LIVE约束。详见[支付协议复核](../payment-protocol-review.md)。

## 取消与订单地址续作（2026-11-06）

POST `/mall/orders/{orderId}/cancel`按ReasonAction接收expectedVersion/reason，始终HTTP202并返回AsyncResult。无付款历史可当次完成关闭并status=completed；有付款历史则status=pending/running/manual，渠道未知时仍保留业务待付与库存。取消命令GET按领域订单及任务实际状态投影，不将“接受申请”的持久命令completed误当渠道关单成功。POST重放返回同一commandId的最新进度；所有操作仍重验本人及账户状态。取消申请后禁止继续付款，客户端取消支付界面本身不调用此接口。

PATCH `/mall/orders/{orderId}/address`接受OrderAddressChange，选择本人有效地址簿记录；按原成交配送规则重新校验禁配和同运费，不套用之后新购设置，不改商品/应付/实收或付款号。发货、有效售后、关闭申请、过期未付及版本冲突均拒绝。原因保留在私有订单地址快照，审计只记录版本、地址ID及前后/原因摘要；该修改接口的响应仍使用脱敏收件资料。`GET /mall/orders/{orderId}`在本人归属校验后，单独返回完整收件电话与地址。本人详情只暴露已实现且状态允许的cancelMallOrder/changeMallOrderAddress操作，以及安全取消/修改地址/超时关闭时间线。后续后台取消/改备注进展见0.4.0补充，正式发货入口仍待实施。

## 后台订单办理与发货前检查（0.4.0，2026-11-06）

当前仍92路径、104操作，新增FulfillmentCheck后共143个schema，不增加业务接口。AdminOrderDetail增加必需fulfillmentCheck（businessReady及blockingReasons的安全code/message）；它只表示当前业务事实是否满足出库前条件，不代表shipMallOrder已经可用，也不代替实际出库时在订单锁内重验。买家详情不含此字段或internalNote。

已注册listAdminMallOrders/getAdminMallOrder/noteMallOrder/cancelAdminMallOrder。列表仅精确订单号、状态及下单时间筛选；时间必须含时区，区间为[from,to)，游标绑定管理员与已应用筛选，稳定倒序分页。列表只返回Order摘要，不把买家账号/内部备注附在每行；详情返回最小buyer.id/displayName、脱敏地址、内部备注及安全时间线。手机号、证件及明确标注的医保/医疗账户等文本输出脱敏，不把原始audit.detail返回客户端。

备注与取消在后台账号锁、当前角色权限及订单锁下核对版本，同键同内容重放，异内容或旧版本409；审计user_id=None且detail.adminAccountId明确身份，备注只记录摘要。后台取消复用买家取消的唯一原单查证链路；无付款历史的本地释放流水标注admin，不冒充买家或系统到期。取消命令仍按实际订单/任务状态投影，接受申请不等于已关闭。

发货检查识别未核实收款、金额/渠道事实不一致、额外付款、待关闭、有效售后、退款/数量变化、明细已售事实不一致、重复发货、收件资料不完整及资金人工待办。已核实售出的正常商品不因当前可售库存为零或后来归档而被重复占用/扣减。正式出库服务尚未实施；后续必须持订单锁调用check_fulfillment(lock=True)，不能信任之前GET结果。refund已变更订单先保守转核实，细分可发数量由售后故事补齐。

releaseMallFulfillment现按宪章4.0.0实现为单订单内部领取：每次重验当前权限、付款/发货/售后状态、版本和履约告知；成功只返回收件姓名、电话、地址、60秒到期时间及审计ID，Cache-Control为no-store，不进入响应重放缓存。未配置现有留存制度引用或经审阅告知版本时仍审计拒绝并返回403。订单和发票管理页已接入短时领取交互，前端构建通过；`VITE_MALL_DATA_RELEASE_UI_ENABLED`默认false，页面交互/60秒清除尚待验收。向微信、承运商或快递100传输原文仍未授权。

## 本地履约接口与订单动作（0.5.0，2026-11-06）

接口数量仍为92路径、104操作、143个schema。当前本地履约子集实现shipMallOrder本地发货登记、correctMallTracking运单更正及confirmMallReceipt本人确认收货；更正请求同时携带expectedVersion（订单）和shipmentVersion（包裹）。唯一包裹约束、订单锁与包裹版本幂等共同防止重复出库及旧请求覆盖。

订单登记时冻结autoReceiveDays并写入autoReceiveAt；系统任务必须显式启用mall worker，按订单锁、包裹版本执行自动收货，发现未决售后则延后一天再次检查。买家只可本人确认，不把物流签收或员工登记转换为本地收货。T055/T062本地切片已实现。

后台当前可以登记已完成的本地发货事实和更正运单；该操作不传输收件资料、不调用快递100。此0.5.0切片时快递100轨迹仍未接入；后续0.6.0实现状态见下节。本项目没有微信平台发货/确认环节。该切片当时`releaseMallFulfillment`固定403；后续按宪章4.0.0改为受运行配置约束的单订单内部领取，当前默认关闭。后台订单响应仍不含收件人原文。自动worker默认关闭，不能据测试配置宣称生产自动收货已经启用。

## 快递100本地查询接口（0.6.0，2026-11-06）

契约仍为92路径、104操作、143个schema；`LogisticsSnapshot.source`标注`fake`、`live`或`null`，让客户端明确区分模拟节点、真实缓存与尚无查询结果。

本人订单GET、后台订单GET读取同一包裹安全快照并共享唯一查询任务和30分钟冷却；后台POST刷新使用实时`mall.shipments.write`校验、包裹版本及持久幂等命令，也不能绕过冷却。接口只接受订单/包裹ID，不接受任意承运商与运单号。所有轨迹文本先限制长度并脱敏电话号码；仅保留时间、描述、状态、粗粒度区域、预测节点坐标和预计到达文本，不保留地图令牌URL、派件员联系方式或供应商原始payload。失败有安全错误码；旧轨迹可标记stale继续展示。

Kuaidi100适配器实现`maptrack.do`表单及签名，在单次截止、响应上限、禁重定向的HTTP客户端内工作；`resultv2=7`，保持`needCourierInfo=false`且不返回`trailUrl`。运行配置默认为fake、不允许出站；production固定返回`config_required/data_release_gate_inactive`，不会调用真实provider。仅development/test且显式开启live与出站开关时调用真实provider，且只发送发货地/收件地的省/市/区县名称（2026-11-11用户授权），缺少任一名称返回`config_required`；测试环境禁止启用真实出站。对快递100明确要求电话核验的承运商（顺丰速运、顺丰快运、中通快递），仅当本订单有效履约同意包含`recipient_contact`时随单发送收件人电话（2026-11-11用户授权），不落库、不回传、不写日志；其余承运商不发送。账户凭据的`repr`隐藏。真实请求、账户额度/订阅保持未验收。

fake/live分支验收证明订单隔离、买家/后台共享冷却、错误状态、电话脱敏、迟到的旧运单结果不能覆盖更正后快照；快递状态显示签收时订单仍是`pending_receipt`，不改变本地收货状态。这些结果不等于真实快递100账户调用或小程序物流页已完成。fake分支返回带明确`source=fake`标记的合成预测路线用于本地展示；真实地图/预计信息需在development/test显式开启live后核验。


## 买家结算安全配置（0.7.0，2026-11-06）

新增公开只读接口`GET /api/v1/mall/checkout/settings`，返回`purchasingAvailable`、`freightMode`、`freightCent`与`policyVersion`，供买家端展示购买开关、读取当前运费规则并按当前政策版本保存地址/创建订单。接口不返回管理员联系方式、发货/退货地址、禁配区域、密钥或任何买家原文资料，响应`Cache-Control: no-store`。当前契约为92路径、104操作、145个schema；实现及测试不代表已部署或开放真实购买。

US2买家端支付结果依本人订单/支付GET查询原号恢复，不依赖支付通知回调。T049/T050/T051可先完成客户端确认中、继续付款和结果页面；T048及T052的本地业务验收独立于生产支付授权，T048通知实现/隔离回归已单独验收。

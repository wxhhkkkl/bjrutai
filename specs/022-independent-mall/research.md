# Research: 自营独立商城

日期：2026-11-04。研究依据为当前仓库只读检查与官方文档；未访问生产数据、未执行支付退款或出具发票。按本地规划技能并行研究绩效及支付隐私，再由主流程核对和整合。

## D01 保留现有三端与依赖

**Decision**：FastAPI/SQLAlchemy异步后端、manageSystem Vue后台、原生微信小程序，沿用MySQL、COS与APScheduler。httpx调用微信，签名使用已受控cryptography依赖；具体安装版本须在实施时锁定并验签测试，不为规划安装SDK。

**Rationale**：当前依赖与宪章已有约束，首期体量不需要拆微服务或新增队列中间件。

**Alternatives considered**：引入Java商城或重做会员/分销体系增加迁移面；Redis/Celery或通用工作流不是首期必要条件。

**Evidence**：`backend/requirements.txt`、`manageSystem/package.json`、`miniProgram/package.json`、项目宪章I–V。

## D02 商城消费独立，不写伪Bill

**Decision**：新增`mall_consumptions`作为商城来源，通过统一投影合并Bill和商城；保持原来源语义。

**Rationale**：`Bill`强制客户关联并有诊费药费字段，普通买家可能无业务客户。无需伪造客户或把商品金额当诊费。

**Alternatives considered**：扩Bill并用合成客户会破坏已确认普通购买及来源独立；仅改绩效总额会漏明细。

**Evidence**：`backend/src/models/bill.py:38`；`consumption_service.py:35`；`contribution_query_service.py:68`；`contribution_dashboard_service.py:144`；`settlement_service.py:39`。

**必须联动**：个人/客户/组织汇总、跨来源明细、latest30、报告导出、可核算月份与小程序预估。统一游标为`occurredAt,sourceType,sourceRecordId`，不能两个列表各取20后伪装全局分页。

## D03 持久化幂等与安全重试

**Decision**：商城写操作跳过现有内存缓存；`mall_commands`唯一`actor_type,actor_id,action,key`加规范化请求摘要；同键同内容返回关联原实体，同键异内容409。业务/渠道资金唯一约束永久保留，不因命令过期重复付退。

**Rationale**：现有中间件进程重启丢失，key不含body，且可能缓存过期权限结果。幂等重放前仍查当前身份权限，不存含敏感原文的完整响应。

**Alternatives considered**：前端禁重复点击或单机缓存不能应对并发、重启与未知渠道结果。

**Evidence**：`backend/src/main.py:22–80`；已有反馈/手工消费持久幂等排除路径可借鉴，但不照抄其领域字段。

## D04 短事务与通知入箱

**Decision**：回调验签、解密并校验主体金额后，短事务durable inbox及处理任务显式提交，成功再204；工作项重复执行安全。普通业务事务采用已有会话约定，渠道回调另有明确提交边界。

**Rationale**：现`get_db`在yield之后commit，不能作为资金通知“已可靠收到”的证明。微信回调有重复/超时，须结合查单。

**Alternatives considered**：先ACK后仅内存处理会丢单；持库存锁等待网络会放大死锁和超时；直接套JWT与统一业务响应不符合渠道协议。

**Evidence**：`backend/src/core/database.py:78–86`；[微信支付通知](https://pay.wechatpay.cn/doc/v3/merchant/4012791902)、[微信退款通知](https://pay.wechatpay.cn/doc/v3/merchant/4012791906)。

## D05 数据库锁、任务与多实例

**Decision**：交易锁固定顺序为期间协调行（涉及绩效时）→订单→支付/售后/明细→按ID排序SKU→对应业务记录。任务领取用`FOR UPDATE SKIP LOCKED`及有期限租约；普通库存/退款额度不能跳过锁。单调版本及唯一事件键防重复应用。

**Rationale**：APScheduler每应用进程都可启动，`max_instances=1`仅单进程，必须数据库去重。订单与退款额度只有串行核实才避免超退。

**Alternatives considered**：只在Python中加锁不能跨worker；用SQLite通过测试不能证明MySQL锁语义。

**Evidence**：[MySQL锁定读](https://dev.mysql.com/doc/refman/8.0/en/innodb-locking-reads.html)说明跳锁适用于队列型表，不能据此忽略业务锁；[SQLAlchemy事务说明](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html)用于明确begin/commit边界。

## D06 渠道未知与关单

**Decision**：out_trade_no、out_refund_no先落库稳定唯一，再调用；超时先查原号。关单先核实未付，外部关单确认后短事务释放；支付成功与关单按渠道证据归并。退款ABNORMAL不释放占用、不默认新退款。

**Rationale**：客户端取消非业务关闭，退款受理非到账。渠道成功本地未知需要可重放。

**Alternatives considered**：换单号立即重试或过期直接回库，可能双扣、超卖、超退。

**Evidence**：[微信退款申请](https://pay.wechatpay.cn/doc/v3/merchant/4012791903)、[小程序支付开发指引](https://pay.wechatpay.cn/doc/v3/merchant/4012791911)。

## D07 现有阶梯及舍入保持兼容

**Decision**：先合并基数再命中下含上不含阶梯，命中比例作用整个基数；个人覆盖优先，组织管理员自己仍可按现有规则参与个人绩效并另取管理绩效。保持`legacy_float_round_v1`：现有`int(round(base_cent * float_ratio))`兼容，规则比例快照及算法版本一并保存。

**Rationale**：改成分段累进或未经验证改Decimal舍入会改变存量数字。新金额仍以整数分保存，计算兼容规则不能偷改。

**Alternatives considered**：分别计算两种来源后相加、独立商城佣金、直接统一新舍入均偏离用户要求。

**Evidence**：`commission_service.py:31–48,193–241`、`models/personal_performance_rule.py`、既有阶梯和个人覆盖测试。

## D08 期间边界显式分来源

**Decision**：商城支付成功UTC时间另保存Asia/Shanghai所得`business_period`；界面按北京时间展示。旧Bill保持原查询期间行为和既有冻结期，不全局替换历史过滤。当前月份默认选择可用北京时间，但旧来源归期须可解释。

**Rationale**：现helper为朴素月界且当前月用UTC，直接全改会移动旧边界单；“统一绩效规则”不授权迁移旧期间。

**Alternatives considered**：商城使用UTC违背新规格；一刀切旧数据迁月超出本轮范围。

**Evidence**：`consumption_service.py:19–32`、`performance_view_service.py:21–23`、`settlement_service.py:39–83`。需新增月末/迟到通知及仅商城月份测试。

## D09 冻结输入证据与审核版本

**Decision**：每核算批次保存结果快照、规则源版本、参与人员及原组织管理范围、所有来源基数及版本、商城订单候选金额和算法版本；未生成结果行的原期计算单元也保存独立证据锚点、原应得0及原因。审核锁期间校验输入版本。源变化先获取同期间协调锁，未冻结则标stale，已冻结才生成差额任务。

**Rationale**：当前结果只存base/ratio/commission/rule_snapshot，缺输入与成员；当前review条件更新不能识别退款后旧估算。没有完整证据不可按当前树重算旧差额。

**Alternatives considered**：只保存规则或仅原sum不足以对管理阶梯重放；老历史证据不全不能伪造回填，改人工核实。

**Evidence**：`models/commission_result.py:21–38`、`models/performance_settlement.py:24–43`、`settlement_service.py:117–139`。

## D10 差额、核销及债权防绕过

**Decision**：差额`C*−C0−累计已审核调整`，锁原期证据锚点逐项生成，存在原结果才另锁原结果；调整唯一键按evidence_id，origin_result_id允许空，原规则/资格证据不足走人工。应用记录将已确认差额分配到后期未核销额度，使用正负净额和债权结余。核销入口同事务锁结果/应用，兑现净额；原commissionCent保留正常绩效含义。

**Rationale**：现核销整行`commission_cent`并归零余额；若只在页面展示负数，核销仍可全额兑现。已核销历史不能回写或凭空扣已兑权益。

**Alternatives considered**：改旧绩效、退款乘当前比例、把负消费放当期阶梯、增加钱包均不适合。

**Evidence**：`commission_service.py:363–427,626–654`；`tests/contract/test_performance_points.py:77–107`。所有小程序/后台余额、导出、查询及核销须统一净额；无调整仍兼容旧字段与行为。

## D11 执行时权限与正确审计身份

**Decision**：商城高风险与所有者读取查询实时DB状态/角色；不复用必须顾问身份的依赖；权限与数据范围同时检验。审计后台操作者用`user_id=None`和`detail.adminAccountId`。

**Rationale**：当前JWT只验签，权限在token中，撤权旧token可继续用；AuditLog外键指users不是admin_accounts。

**Alternatives considered**：仅隐藏按钮或信旧JWT不满足FR-088；把admin id写users外键会串身份。

**Evidence**：`api/deps.py:32–56,93–120,147–166`、`models/audit.py:23–33`、`feedback_service.py:307–319`。

## D12 履约资料规则适配

**Decision**：默认查询与地址回显继续脱敏；拟采用订单级、目的限定、单次短时履约交付，不提供通用查看客户原文。完整电话/地址交付存在必要窄例外，写成[规范提案](governance-proposal.md)，不修改现行宪章、不在研究阶段开权限或传资料。

**Rationale**：实际快递必须有可用收件资料，而宪章IV明确任何API输出均脱敏。即使后端直连承运商也要明确规范及告知，不可用已有外部医院原文请求当自动授权。

**Alternatives considered**：永久公开导出、统一原文GET、借用医疗客户资料均拒绝；首期尚未选定承运商，不虚构已接面单服务。

**Evidence**：宪章IV；现`miniProgram/models/legal-document.js`未完整覆盖商城收件、支付、履约与票据目的；现`consent.py`场景需新增版本证据。规范实施门禁不影响非敏感模块任务规划。

## D13 发票文件私有交付

**Decision**：新文件归属表，票据仅PDF≤10MB；证据图片JPG/PNG≤5MB每单最多3张。只存object key、checksum、大小、归属，不接受任意fileUrl。签名上传后HEAD核验，发放短时GET前重验订单权限，发票签名默认120秒。

**Rationale**：通用上传返回永久fileUrl；反馈专用已有私有前缀/HEAD/签名GET可借鉴，但无凭据直接返回存在的测试降级不能用于生产票据。

**Alternatives considered**：永久URL、直接接受外部PDF、未验证对象即关联均可泄露或伪造。

**Evidence**：`cos_client.py:112–182`；桶private及凭据需上线实际检查，代码本身不能证明当前私有。

## D14 发货登记与收货确认

**Decision**：员工在商城后台登记本地包裹及运单即完成发货登记；本项目不存在微信平台发货环节，不对接微信发货API，也不需要任何平台侧人工录入或回填。快递100独立查询轨迹。本地出库、买家确认收货和资金结算分开，物流签收或员工登记不能代替买家确认。

**Rationale**：2026-11-11用户确认微信平台发货概念不存在于本项目，此前基于“必须向微信平台录入”的人工登记方案作废。只保留商城本地发货事实，可减少无业务价值的状态、审计和操作步骤。

**Alternatives considered**：曾评估微信后台人工录入或发货API，但两者均不适用于本项目，不再作为需求或验收条件。

**Evidence**：2026-11-09曾依据[微信支付小程序开发指引](https://pay.wechatpay.cn/doc/v3/merchant/4012791911)和[官方常见问题](https://pay.wechatpay.cn/doc/v3/institution/4019800055)评估“后台人工录入或调用API”两种方式；2026-11-11用户确认本项目没有微信平台发货环节，两种方式均不再适用，原决策作废。无真实平台账号或实际操作证据。

## D15 数据库与上线策略

**Decision**：新增表及可空附加字段，Alembic按现head023继续编号；首期不删原表、不回填伪冻结证据。购买开关默认关；有交易后回退仅停新购，保留存量资金及售后任务。

**Rationale**：生产startup当前有`metadata.create_all`，不能替代迁移；需新增显式生产禁用自动建表检查，隔离测试不触生产库。

**Alternatives considered**：新购一开就接生产、降级drop表、用SQLite模拟资金并发均不能满足标准。

**Evidence**：`main.py:89–96`、`migrations/versions/023_article_videos.py`、`tests/conftest.py`。

## 研究结论与边界

技术选择均已落定，无占位澄清项；剩余是明确的阶段条件：资料窄例外规范生效、平台账号与发货字段核验、经营及开票条件、用户UI参考图。没有为这些条件提前操作生产、公开文件、修改宪章或增加实际权限。


## D16 用户补充快递100：后端查询、缓存与按票限流

**Decision**：接入已开通的快递100地图轨迹查询，可信包裹决定查询对象；后端凭据、缓存与单票限流，不让小程序直调。地图展示等待风格参考，预计信息只作参考，订阅权益未核实不先建回调。

**Rationale**：用户提供了可用服务方向，原纯运单占位不再足够；频繁打开订单不应产生重复外部查询。轨迹签收不是微信收货或退货验收。

**Alternatives considered**：小程序带密钥直查、高频定时扫描所有运单、将签收直接完成订单、自动加入面单/寄件均不采用。

**Evidence**：[快递100补充与官方来源](logistics-integration.md)。账户密钥及具体权益未读取，查询真实资料前仍核验目的及适用规范。

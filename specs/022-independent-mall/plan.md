# Implementation Plan: 自营独立商城完整闭环

**Branch**: `022-independent-mall` | **Date**: 2026-11-04 | **Spec**: [spec.md](spec.md)  
**Input**: `specs/022-independent-mall/spec.md`、业务规则及验收矩阵。

## Summary

在当前项目内增加独立商城业务模块，不另建会员、组织树或独立提成规则。使用现有后端、管理后台、原生小程序与MySQL，商品订单独立建模；收退款采用持久化命令、渠道通知入箱及数据库任务恢复；商城消费作为新来源并入现有读取和绩效引擎，冻结输入可重放，跨月差额连同既有积分核销约束一起落地；发票按人工真实开具、私有票据交付与红冲关联实施。

本计划阶段产出研究、模型、接口契约、验证与上线方案；后续任务阶段已单独生成[tasks.md](tasks.md)。两个阶段均未编写业务代码、运行迁移或连接生产。小程序仅设计数据及交互契约，视觉设计等待用户本轮参考图。

主要文件：[研究决策](research.md)、[数据模型](data-model.md)、[接口契约](contracts/README.md)、[本地验证指南](quickstart.md)、[履约资料规范提案](governance-proposal.md)、[规划检查](checklists/planning.md)。

## Technical Context

**Language/Version**: Python 3.11+；后台与小程序沿用JavaScript，不引入TypeScript或跨端框架。  
**Primary Dependencies**: 现有 FastAPI 0.115.0、SQLAlchemy 2.0.35 async、Pydantic 2.9.2、Alembic 1.13.2、httpx 0.27.2、APScheduler 3.10.4；Vue 3/Vite/Element Plus/Pinia/Axios；原生小程序及现有Vant Weapp。复用既有依赖，不升级整套技术栈。支付签名验签使用已安装 cryptography 能力，需显式声明受控直接依赖版本并验证；不临时从未知仓库安装支付SDK。  
**Storage**: 现有MySQL 8.0 / InnoDB，新增商城与绩效证据表；COS私有对象；数据库凭证及商户密钥仅环境注入。开发测试库与生产严格分离，TLS上线核验，不因代码注释存在而声称TLS已配置。  
**Testing**: pytest/pytest-asyncio契约、单元与集成；新增独立MySQL并发/迁移测试，SQLite原测试不能证明InnoDB锁安全；后台Vitest；小程序现有Node测试与后续微信双平台真机验收。  
**Target Platform**: 当前Linux Docker后端部署、浏览器管理端、iOS/Android微信小程序；单应用部署，数据库工作队列支持多进程去重。  
**Project Type**: 已有三端业务扩展，非新站点、非微服务重建。  
**Performance Goals**: 500在售商品、10,000历史订单、20同时用户；主要查询p95≤2秒；100次末件争抢最多一单；同事实20次重复/乱序无二次副作用；可靠核实后60秒内前后台一致。  
**Constraints**: 不改历史冻结数值、不默改旧账单期间或舍入、不建立钱包、不复制原规则；消息与未知结果可恢复；商品款/运费/净收/绩效/票据金额分离；UI风格等待用户。  
**Scale/Scope**: 首期十个后台页面、九条用户故事；表与路由范围见模型和契约，不引入营销或统计中心。

## Constitution Check

*规划前后均检查；“规划可交付”不等于所有实施前置条件已满足。*

| 原则 | 研究前结论 | 设计后结论及证据 |
|---|---|---|
| I 测试先行 | 通过：仅做文档，不写生产代码 | 设计已补齐：T005规划一条命令自动准备隔离库、迁移、测试及清理，不要求人工建库；实际通过仍须执行证据 |
| II API优先 | 已定义契约；外部通知应答与现宪章存在冲突 | 未通过通知子项：见[独立草案](protocol-governance-proposal.md)。G-PROTOCOL正式落实前不得实现/部署两个通知端点；其它业务接口仍统一响应，非通知模块可先行 |
| III 三端分离 | 通过：复用现有三端 | 规划通过；金额、权限、状态在后端；前端仅展示和输入校验 |
| IV 完整性、脱敏和审计 | 存在已登记适配：真实履约交付需要必要收件资料 | 有理由的规范变更提案已形成，现宪章未改。脱敏查询、无原文通用API、私有文件、审计、迁移设计符合现有规则；涉及完整收件资料向履约方及开票必要信息向财务交付的功能实施前须按提案落实规范。此子门禁尚未生效，禁止标成完全通过 |
| V 简洁 | 通过：无微服务/多商户/营销 | 规划通过；数据库事务与持久化任务是资金可靠性所需，不加Redis、消息中间件或通用工作流平台；复杂度理由见下表 |

宪章IV适配不是未解决的技术选型：已明确采用订单级、目的限定、最小必要的交付方案并给出规范提案。后续可拆分不涉及原文交付的任务；不能以规划完成越过该实施门禁。正式规则适配前不得提供这些原文领取/导出或向第三方真实传输资料。

宪章II通知应答冲突仍是待正式治理的阻塞项，独立草案未生效；不因本轮修订而宣称现宪章已全面对齐。T048/T073中的通知实施受G-PROTOCOL约束。

## Project Structure

### Documentation (this feature)

```text
specs/022-independent-mall/
├── README.md / spec.md / product-rules.md / acceptance.md
├── plan.md
├── research.md
├── data-model.md
├── governance-proposal.md
├── quickstart.md
├── contracts/
│   ├── README.md
│   └── openapi.json
└── checklists/
    ├── requirements.md
    └── planning.md
```

### Source Code (repository root; planned, not created this round)

```text
backend/
  src/models/mall_catalog.py, mall_trade.py, mall_finance.py, mall_operations.py
  src/models/mall_consumption.py, performance_evidence.py, performance_adjustment.py
  src/schemas/mall_*.py, performance_adjustment.py
  src/api/v1/mall_*.py, admin_mall_*.py, mall_gateway_callbacks.py
  src/services/mall_catalog_service.py, mall_checkout_service.py
  src/services/mall_order_service.py, mall_aftersale_service.py
  src/services/mall_payment_service.py, mall_invoice_service.py
  src/services/mall_job_service.py, mall_reconciliation_service.py
  src/services/performance_evidence_service.py, performance_adjustment_service.py
  src/integrations/wechat_pay_client.py, wechat_shipping_client.py, kuaidi100_client.py
  src/services/mall_logistics_service.py
  src/tasks/mall_tasks.py
  migrations/versions/024_mall_core.py, 025_mall_finance.py, 026_performance_evidence.py
  tests/contract/test_mall_*.py
  tests/unit/test_mall_*.py, test_performance_adjustments.py
  tests/integration/test_mall_*.py
  tests/mysql/test_mall_concurrency.py, test_mall_migrations.py
manageSystem/
  src/api/mall.js, stores/mall*.js, pages/mall/*
  src/router/index.js, constants/permissions.js, App.vue（按现有导航扩展）
miniProgram/
  services/mall-*-service.js（允许先做服务契约与测试）
  pages/mall/* 及商品/购物车/订单/售后/开票页面（UI阶段之后）
```

**Structure Decision**: 仓库实际后台目录是 `manageSystem/`，不用旧README中的 `admin/` 新建另一项目。路由、权限、审计、文件与任务按已有模式扩展；服务按领域拆分，避免一个数千行商城服务。上列迁移号是当前仓库head023后的计划，实施时重新核验迁移head，不盲目覆盖并行新增迁移。

## Phase 0: Research Decisions

已从当前源码及官方规则完成[研究决策](research.md)。关键结论：

1. `Bill`有强制业务客户及诊药字段；新商城消费独立来源，统一聚合、明细、月份、报表及前后台入口，不伪造客户。
2. 现有幂等中间件是进程内缓存，不能承担下单退款；所有商城写路径显式绕开，用持久化命令和内容摘要。
3. 渠道调用不放在持锁事务内；通知先验签核实并持久提交，再应答，工作项至少一次执行且业务副作用唯一。
4. 核算冻结缺输入、范围和算法版本；新期间冻结前补快照。旧冻结证据不足转人工，不用当前组织树猜历史。
5. 现有积分核销可兑现整行绩效；新增差额须约束未来可核销净额，历史已兑不回写，不创建钱包。
6. 商城按北京时间保存业务月份，旧Bill保持既有期间语义；新功能不借机移动旧账单月份。界面使用北京时间展示，明确来源期间策略。
7. 用户已开通的快递100轨迹查询按[补充设计](logistics-integration.md)接入，独立缓存/限流；微信平台发货/收货管理按商户及小程序实际适用规则接入；本地发货事实与平台同步分别存储，平台失败重试，不重复出库。
8. 发票沿用人工真实开具，文件私有与短时授权；通用上传返回永久URL不能直接作为票据交付方案。

## Phase 1: Design & Contracts

### 1. 事务与外部调用

- 下单：锁命令→校验有效用户与最新报价→按SKU ID固定顺序锁库存→占用→保存订单明细及任务→提交。无网络请求占用库存锁。
- 支付：锁订单建立唯一活动支付请求及任务，提交后调用微信；超时先查同商户单号。核实成功的事务同改支付、订单、库存占用、商城消费及任务，重复事件无二次入账。
- 取消：本地进入关单待核实，外部查单/关单；只有确认未付且关闭才释放。成功支付与取消竞争都重新锁订单按已核实事实归并。
- 售后：锁订单及明细、额度和SKU关联，创建一次占用；审核、退款提交沿用占用，发货按同订单锁互斥。
- 退款：提交前形成稳定商户退款号；渠道受理非成功，只有核实成功才更新成功退款累计、候选绩效与票据待办。入库另以实物验收/未出库取消事件控制。
- 回调（G-PROTOCOL正式采纳后才可实施）：目标为专用短会话先验签/解密及金额主体匹配，durable inbox明确提交后204。失败不返回成功；异步工作项处理中断可恢复。常规API不能依赖yield结束后commit满足回调先持久化要求；未采纳时只做隔离失败用例/非通知服务，不先实现通知端点。
- 任务：沿用APScheduler触发轮询，任务表用数据库租约、固定事件键和重试时间，MySQL `SKIP LOCKED`只用于领取队列，不用于跳过库存或退款额度锁。

### 2. 绩效与兑现一致性

统一消费读取合并旧Bill及商城来源；客户、个人、组织、最新明细、报表、可核算月份全部同源。商城无客户仍能交易；补归属按原期间，不记到当前阶梯。

月度核算保存输入指纹与单调业务版本。审核锁批次并核对核算版本，若退款/归属/规则/组织已改变则409要求重算，不把旧结果冻结。锁周期行序列化来源变更与审核，确保“先变更后审核”和“先冻结后调整”均确定。

冻结快照包括各结果、规则来源/版本、原人员及管理范围、各来源基数与商城明细、舍入算法版本。原期参与人即使因未命中阶梯未生成结果行，也保存独立证据锚点，明确原值0及未生成原因，不向冻结结果集合补零行。调整按锚点唯一，origin_result_id可空；缺原资格/规则证据转人工，不用后来规则。跨期模拟固定这些输入；差额审核与应用分开，后期正常绩效不变，调整净额单列。既有核销接口在同一锁序内扣除分配债权后才可兑现；已核销原值保留，不能仅在页面扣减。

### 3. 权限与隐私

商城新增依赖实时查询用户/后台账号状态和角色权限，不能只相信JWT内旧权限。所有者和组织范围在查询中约束，文件签名发放时再次校验。

原文收件信息只允许订单履约目的、授权操作与短时使用，按[规范提案](governance-proposal.md)阶段生效；默认API只返回脱敏电话。地址编辑通过保持原值或提交新值，不从后端回显完整电话。支付密钥仅环境注入，资金签名、完整原文不记普通日志。审计后台操作者用`detail.adminAccountId`，不把admin表ID写入users外键。

### 4. 平台与票据

微信支付能力、商户与小程序关联、HTTPS回调、公钥或证书轮换、平台发货适用条件等进入上线检查。平台确认收货与本地用户确认分别留证，不用定时器伪造平台确认。无自动轨迹时明确只展示真实运单。

`G-LIVE-SHIPPING`定义为G-LIVE下的“微信发货协议预核验”子项：T054先记录官方字段、适用条件、当前账号能力声明/未验证项及可审阅字段映射至`shipping-protocol-review.md`；不需要真实发货。T056按该映射实现fake适配器，不得猜字段；缺核验资料时保持明确未验证，不完成实际协议映射或报同步成功。T131在最终阶段核验当前真实账号、权限和平台结果。子项范围记录不等于G-LIVE整体或真实出站已获放行。

开票申请与实际票据独立版本；财务领取、退款与回传均锁订单和申请校验，不阻止记录已实际出具的票据。更正/红冲链不删历史，净有效覆盖防重复开。文件只存私有object key，核实归属、类型大小与实际上传后才绑定，不接受任意外网URL。

## Phase 2: Implementation Sequence (planning only)

| 顺序 | 可验证交付 | 前置/出口 |
|---|---|---|
| M0 基础安全与契约 | 实时鉴权、命令幂等、inbox/jobs、只增迁移、隔离MySQL测试 | 先失败用例；无真实渠道副作用 |
| M1 商品至收款 | 分类SKU、库存、地址、购物车、报价、订单、微信支付查关单 | AC-001–015；末件、乱序、重启恢复通过 |
| M2 履约至退款 | 售后额度、审核、包裹、实物验收、原路退款、平台同步 | 原文交付规范实施门禁；AC-016–026通过 |
| M3 消费与绩效 | 全入口统一来源、月份、冻结证据、差额审核应用及核销净额 | AC-027–033及旧核销回归；上线不得漏掉核销路径 |
| M4 发票与资金核对 | 私有票据、开票领取/回传、红冲重开、日账差异待办 | AC-034–042；按平台真实结果验收 |
| M5 管理后台与非视觉小程序服务 | 十页信息交互、数据服务与状态测试、权限导航 | 不实现小程序视觉；后台复用现有组件 |
| M6 小程序UI设计 | 先提醒用户，取得本轮风格参考图再设计 | 用户明确约定；无图不得出视觉稿或页面样式 |
| M7 联调与开放购买 | AC-001–053、Q-01–10、旧功能回归、经营及平台核验 | 真实渠道与票据证据及G-PROTOCOL/G-DATA正式落实；未通过不开放购买 |

阶段可以按依赖并行编写测试，但不得“前端演示成功”替代资金事实。后续 `/speckit.tasks` 已生成独立任务表，实施仍须按任务依赖及条件执行。

## Migration, Rollout & Recovery

采用expand-first迁移：商城表及现有表可空附加字段先上线，保持旧接口字段含义；旧冻结结果不造伪快照。配置`MALL_ENABLED`、`MALL_PURCHASE_ENABLED`、`MALL_GATEWAY_MODE`（test/live）以及独立出站任务开关；默认为关闭购买，测试模式绝不使用生产凭证。

先部署兼容代码与新增表，初始化空配置及最小权限，核验迁移一致性→隔离验收→填经营/平台条件→灰度→开放购买。生产不得用`create_all`代替Alembic；需给生产启动禁用自动建表的显式配置与检查，不重构无关启动流程。

回退优先关闭新购和外部新请求，保留已支付订单的查询、发货、退款及任务恢复；线上已有资金记录不做drop表或删除事务历史。旧版应用不能再启动含商城数据却不理解其任务和调整的版本；预留兼容修复版与备份恢复方案。任何余额/退款/已开票差异先核实，禁止直接回滚库伪造撤回渠道交易。

## Complexity Tracking

| 有理由的额外机制 | 必要性 | 未采用的更简单方案及原因 |
|---|---|---|
| 持久命令、inbox和任务表 | 进程重启/重复通知/未知请求下资金安全 | 内存缓存与一次同步调用无法恢复；无需消息中间件 |
| 冻结输入、差额及应用记录 | 原规则重放及既有核销防绕过 | 直接重算历史或只显示负数会错误或可超兑 |
| 少量现有绩效接口兼容扩展 | 全源展示与月份、兑现一致性 | 仅新增商城合计会漏明细/月核算入口及核销 |
| 私有文件授权与订单级履约交付规范提案 | 真发货和真实票据交付 | 永久公开文件或通用原文查看违背现有隐私规则；未生效前不执行交付例外 |
| 原期零结果证据锚点 | 补归属跨阶梯时可能没有原结果行 | 使用现有证据表保存原期资格/规则和原值0；不新建表，不补写已冻结结果 |

## Delivery Status

本计划描述拟实现业务；此前文档阶段未实施业务。当前已开始Setup测试工具和契约检查，实际进度与阻塞见[实施记录](implementation-log.md)。仍未完成生产业务接口、新迁移、渠道接入或真机验收；规范例外按条件单独处理。


## Task-stage Supplement: 快递100

用户补充服务已开通，首期物流不再仅保留“未接轨迹”占位。新增快递100适配、缓存/单票限流与三个订单级查询/刷新契约；原101操作扩至104。28表不变，仅包裹附加安全轨迹快照及更新字段。地图视觉仍等待参考图，订阅/面单不自动加入；原文校验信息向物流查询服务商交付同样按最小目的处理，G-DATA适用时不得绕过。详见[补充](logistics-integration.md)。

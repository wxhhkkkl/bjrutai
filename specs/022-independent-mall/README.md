# 022 自营独立商城产品文档

更新：2026-11-05；分支：`022-independent-mall`；阶段：共享基础完成，商品后端与小程序数据服务已实施，后台页面与小程序视觉待后续。

| 文档 | 用途 |
|---|---|
| [实施记录 implementation-log.md](implementation-log.md) | 共享模型、024–026迁移、权限/命令/事件/任务/文件/配置及三端隔离验证证据 |
| [修订复核 remediation-review.md](remediation-review.md) | 5项分析问题的处理、验证范围及尚未解除的治理条件 |
| [外部通知协议草案 protocol-governance-proposal.md](protocol-governance-proposal.md) | 宪章II冲突、限定例外及G-PROTOCOL；未采纳、未生效 |
| [开发任务 tasks.md](tasks.md) | 135项任务、依赖、39项可并行标记、分故事独立验收与阶段条件 |
| [覆盖追踪 traceability.md](traceability.md) | 104个操作、94条需求、53项业务验收的任务归属 |
| [机器任务表 tasks-map.json](tasks-map.json) | 可检查的依赖、接口归属、28表分工与待执行状态 |
| [物流接入 logistics-integration.md](logistics-integration.md) | 用户已开通快递100；查询缓存、频率、异常与隐私边界 |
| [任务检查 checklists/tasks.md](checklists/tasks.md) | 任务格式、依赖、覆盖及文档静态验证；不等于实现通过 |
| [实施计划 plan.md](plan.md) | 三端架构、事务、衔接、分阶段交付、验证与回退 |
| [研究决策 research.md](research.md) | 现状证据、16项技术决策（含物流补充）、官方来源与取舍 |
| [数据模型 data-model.md](data-model.md) | 28张新增逻辑表及现有表兼容附加、状态与不变量 |
| [接口契约 contracts/README.md](contracts/README.md) | 机器可读契约、操作索引、幂等权限、旧接口兼容 |
| [验证指南 quickstart.md](quickstart.md) | 隔离测试、故障、平台联调及上线回退，均为后续操作 |
| [规范适配提案 governance-proposal.md](governance-proposal.md) | 收件/开票必要资料的目的限定交付；未修改宪章或开权限 |
| [规划检查 checklists/planning.md](checklists/planning.md) | 文档契约检查结果与明确的实施门禁 |
| [主规格 spec.md](spec.md) | 首期范围、9条用户故事、94条功能需求、实体、12项成功标准、明确假设 |
| [业务规则 product-rules.md](product-rules.md) | 十个后台页面、字段、金额、库存、状态、退款、绩效、发票、权限、非视觉页面需求及冲突登记 |
| [验收 acceptance.md](acceptance.md) | 金额/阶梯/票据样例、53项业务验收、10项质量验收、需求对应 |
| [质量检查 checklists/requirements.md](checklists/requirements.md) | 16项规格检查结果与下一阶段输入；不等于实现测试通过 |

## 已确认边界

用户明确排除营销/统计/客服中心、商品品牌/属性管理/评论；商城消费纳入现有绩效；包含发票闭环；按二八原则完成收款到交付、退款、票据及核算链路。

现有绩效部分退款全额计入，因此未采用上版净额建议。商品款和运费分开、运费默认不计绩效、收货/售后期限等作为显式设计默认，不能误记为用户逐项批准。

## 下一阶段

产品规格、技术规划、契约和任务拆分已完成；28个模型、024–026迁移和共享基础服务已实施，真实MySQL环境已获授权并运行。统一入口串行验证隔离数据库、后端、管理后台和小程序；精确结果见实施记录。商品、下单、支付、退款和绩效业务故事仍待后续实施，未自动提交或部署。

`/speckit.analyze`发现的5项问题已做文档修订，复核结论见修订报告。C1的规范治理尚未完成：G-PROTOCOL未生效，两个微信通知端点不得实施/部署；非通知基础、商品等模块可先行。收件/开票原文资料的G-DATA提案仍未生效。不能据文档修订宣称全商城可实施或投产。

当前计划契约0.3.0为92路径、104操作、142个schema；本轮在设置schema增加可选退货指引，操作数量不变。任务仍135项、39项[P]，未新增营销等业务。订单详情和绩效核算业务服务尚未实现；共享基础通过不等于商城交易闭环或真实渠道联调完成。

用户补充的快递100已开通信息已纳入首期；三个订单级物流接口及AC-046–051同步进入契约和任务。服务开通不代表订阅、面单、账户额度或真实出站已核验。

**进入小程序UI视觉设计前先提醒用户，等待本轮风格参考图。** 本包只定义页面用途、信息、操作、失败及未知状态，不指定配色、字体或视觉布局，不生成原型图，不修改现有页面样式。

## 依据及证据边界

- 本轮用户商城要求、确认的绩效要求和发票讨论。
- [分析方案 V1.1](../../../商城设计参考/2026-11-04/独立商城系统功能设计-V1.1.md)：包含参考后台当前实查及截图；参考列表为空，未完成真实资金操作验证。
- [现有绩效规格](../008-performance-calculation/spec.md)、[消费口径规格](../009-consumption-metric/spec.md)：月度审核冻结、部分退款全额口径。
- [现有消费计算](../../backend/src/services/consumption_service.py)、[现有绩效计算](../../backend/src/services/commission_service.py)：已核对个人覆盖、当前组织范围及冻结结果行为。来源代码是现状证据，不作为新功能实现。
- [项目宪章](../../.specify/memory/constitution.md)：权限、脱敏、审计及后续实施质量要求。
- [税务发票信息说明](https://shanghai.chinatax.gov.cn/zcfw/rdwd/202402/t470676.html)、[红字数电发票说明](https://www.chinatax.gov.cn/chinatax/n810356/n3010387/c5236346/content.html)：支持发票真实信息与红冲关联设计，具体税目税率由财务确认。
- [微信退款说明](https://pay.wechatpay.cn/doc/v3/merchant/4012791903)：支持受理与到账分开、原退款请求安全重试的业务要求。

文档检查通过不代表线上状态、外部能力、交易或真机测试已验证。后续文档以用户最新决定更新，不变更旧分析文件作为历史记录。

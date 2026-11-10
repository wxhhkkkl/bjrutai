# 商城跨域验收结果

更新：2026-11-08；任务：T128；验收标准：AC-045。

## 结果

通过本地 SQLite 跨域验收。测试通过实际商城地址、报价、订单接口创建同一笔订单，以合成的微信支付成功事实入账，再串联售后、绩效、发票和资金对账。跨域回归 6 个文件 **10 passed**；相关测试文件 Ruff 检查、格式检查和 `git diff --check` 通过。

| 环节 | 本地验收证据 |
|---|---|
| 购买与履约 | 地址 → 报价 → 下单 → 合成支付成功 → 发货，保留唯一订单号和支付单号；同一订单仅一条支付事实和商城消费来源。 |
| 退货退款 | 全量退货申请、审核、运回、验收及成功退款；退款引用原支付和订单，商品款退款后订单金额、售后数量、库存流水和绩效消费来源一致。 |
| 发票 | 同一开票申请记录蓝票；退款后红票引用原蓝票，红冲金额等于成功退款金额，蓝票减红票覆盖额等于支付额减退款额。 |
| 绩效与核销 | 冻结期补入支付时有效的历史归属，审核正向差额并在后续期核销；退款后来源绩效基数归零，再审核对应负向差额。调整记录引用同一商城消费来源，触发版本递增。 |
| 日对账 | 按北京时间的支付成功日、退款成功日创建并关闭日账批次；若测试跨越北京时间午夜，则分日对账。批次实收/退款合计与唯一的本地成功事实相等。 |
| 唯一事实与关联 | 断言订单仅一笔支付、一笔退款、一条商城消费来源、一个售后申请、一个开票申请和一条蓝/红票链；各实体通过订单、支付、售后、消费来源、原蓝票、差额触发源和对账金额互查。 |

测试命令：

```sh
cd backend
.venv/bin/python -m pytest \
  tests/integration/test_mall_end_to_end.py \
  tests/integration/test_mall_order_creation_flow.py \
  tests/integration/test_mall_refund_flow.py \
  tests/integration/test_mall_invoice_flow.py \
  tests/integration/test_mall_performance_flow.py \
  tests/integration/test_mall_reconciliation_flow.py -q
```

## 验收边界

支付结果、蓝票/红票PDF元数据、退货物流信息及渠道日账单都是本地合成数据；未调用微信支付/退款、税务平台、COS、快递100或生产数据库。T108已按用户确认规则以经办人上传/确认作为有效依据，不要求税务真伪核验；生产COS仍待T131核验。隔离 MySQL 并发/恢复及单次耗时见对应任务记录；生产容量/稳定性和真实渠道仍待平台核验。测试运行出现仓库既有的 pytest-asyncio、SQLAlchemy、Pydantic、JWT 和 `crypt` 弃用告警，不影响本次通过结果。


# 既有系统回归与管理端构建（T130）

更新：2026-11-08；验收标准：AC-044。

## 回归结果

后端执行28个定向回归文件，**292 passed，56.08秒**。范围包括：

| 既有链路 | 覆盖文件 |
|---|---|
| 登录、绑定和延迟认领 | `contract/test_auth.py`、`contract/test_binding.py`、`integration/test_auth_flow.py`、`integration/test_binding_flow.py`、`integration/test_deferred_customer_binding.py` |
| 医院同步 | `contract/test_sync.py`、`integration/test_sync_flow.py` |
| 手工消费与消费归因 | `contract/test_admin_manual_consumption.py`、`integration/test_admin_manual_consumption_flow.py`、`unit/test_manual_consumption_service.py`、`unit/test_consumption_service.py` |
| 内容 | `contract/test_articles.py`、`contract/test_article_videos.py`、`integration/test_article_flow.py`、`integration/test_article_video_flow.py`、`unit/test_article_video_service.py` |
| 绩效、冻结、核销、结算和导出 | `contract/test_performance_points.py`、`contract/test_admin_performance.py`、`contract/test_admin_performance_rules.py`、`contract/test_reports.py`、`integration/test_performance_settlement_flow.py`、`integration/test_mall_performance_flow.py`、`integration/test_mall_freeze_race.py`、`unit/test_commission_freeze.py`、`unit/test_performance_adjustments.py`、`unit/test_settlement_service.py`、`unit/test_settlement_task.py`、`unit/test_mall_export_service.py` |

首轮回归中，`test_reports.py::TestSettlementReportStatusSync::test_review_updates_report_status`返回409“绩效规则缺失但存在结果，请人工核实原始规则”。该用例的旧夹具插入了绩效结果，却没有匹配的有效规则和消费来源。冻结证据检查拒绝此数据是正确行为；测试夹具现已补齐有效规则和匹配账单，没有修改该安全检查。单测与全部28个文件复跑通过。

## 管理端构建

在`manageSystem`执行`npm run build`，Vite成功构建生产产物，转换2581个模块，用时5.95秒。构建输出有依赖注释解析、`js-sha1`使用`eval`、`http.js`同时动态/静态导入和主chunk 1,121.82 kB告警；本次构建仍成功。后端回归另有pytest-asyncio、Pydantic、SQLAlchemy、JWT及`crypt`弃用告警。 `tests/contract/test_reports.py` 的Ruff/格式检查仍有基线风格问题（12条E501、3条I001、2条F401；原HEAD文件也未通过格式检查），不影响本次292项功能回归。

本项为本地合成数据和本机构建验收；没有连接医院同步服务、微信、生产数据库或外部商城服务，也没有部署、提交或推送。

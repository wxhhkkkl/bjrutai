# Quickstart & Validation: 自营独立商城

更新：2026-11-10。这是实施/验收操作指南，不构成投产许可。商品浏览、购物车/结算/支付状态、本人订单/物流、售后、绩效和发票主要页面及本地服务切片已实现；T129记录隔离MySQL并发/恢复，T130记录既有系统回归和管理端构建，T132有40项本地小程序集成通过。生产数据库当前版本、真实平台和经营能力未经核验；仓库迁移head记录为038，但不能推断生产已部署版本。T131已核验商城/购买、支付出站、快递100和存储开关关闭/fake；仓库模板中的worker默认为关闭，真实环境worker状态尚未核验。支付/退款通知端点已完成本地实现与隔离回归（T048）；T132真机验收已由用户确认完成，细项未提供；真实渠道验收仍待完成。经营及平台门禁见[发布准备](release-readiness.md)，发布步骤与回退限制见[运行手册](rollout-runbook.md)，实际证据见[实施记录](implementation-log.md)。

后台订单续作：本地前端入口/admin/mall/orders，需实时mall.orders.read；备注与未付款关单另需mall.orders.write。订单号精确匹配，下单日期转UTC请求、结果按北京时间展示；筛选后重新分页，游标不能跨筛选复用。详情展示后台最小买家身份、脱敏收件信息、安全时间线、内部备注及发货阻塞原因。只读人员不显示写按钮，后台仍重验；只有订单权限也能进入商城菜单，不要求先取得商品权限。单订单收件资料领取API已实现，但生产开关默认关闭且后台页面未接入；未配置留存制度引用/审阅告知版本前不得启用。

备注/取消的未知结果只重试原正文/原幂等键，页面内跳转在确认结果前阻止；切换订单读取忽略迟到的旧响应。该原请求恢复仍限当前页面生命周期，不声称关闭浏览器后已持久保存。取消返回pending/running/manual不提示已关闭，可读取原命令进度。发货页面和资料领取按钮尚未接入；领取API每次按新事件重验且不重放响应。页面接入后须在`expiresAt`（60秒）清空原文，禁止本地持久化。发货前businessReady结果只供核实，发货执行时必须在订单锁内重新验证。

支付预付令牌使用独立的MALL_PREPAY_KEYS（key ID到base64url编码32字节AES密钥的JSON映射）及MALL_PREPAY_ACTIVE_KEY加密；更换写入key时保留仍有密文使用的旧key。与商户API私钥、平台验签公钥分开配置，不提供默认密钥。MALL_WECHAT_NOTIFY_URL保持空值；真实账号/域名条件及具体授权满足前不启用资金出站。MALL_GATEWAY_CALLBACK_ENABLED默认false，T048本地回归已通过，但仍不登记生产通知地址，直至G-LIVE及具体授权具备。现有订单恢复不依赖新购开关；缺原支付主体凭据时停止并转人工，不能换商户重建付款身份。

## 1. 当前可检查的产物

- 阅读[计划](plan.md)、[模型](data-model.md)、[研究](research.md)。
- `contracts/openapi.json`可以直接解析并检查引用、operationId、请求/响应与权限；`operation-index.md`供产品及前后端审阅。
- [主验收](acceptance.md)AC-001–053、Q-01–10是后续验收入口，新增可靠性场景见第4节，物流专项见第8节。
- 当前已验证隔离工具、模型、迁移、契约检查及兼容回归；未连接生产或外部业务渠道，实际证据见实施记录。

本地配置为PowerShell版Spec Kit但环境未发现`pwsh`，因此规划阶段按setup-plan的同等步骤读取feature.json、核对分支并复制计划模板；任务阶段等价核对活动目录及必要输入。没有安装PowerShell或改变项目脚本。

## 2. 实施前条件

1. 沿用当前`022-independent-mall`分支及活动feature，保留原规格更改，不新建另一商城功能目录。
2. 按TDD先写失败契约与业务测试，再实现最小切片，测试不能只镜像代码分支。
3. 使用一次性本地/隔离MySQL8测试库，库名必须以`bjrutai_mall_test`开头、明确允许的本地或隔离host；测试fixture在任何create/drop前核实，不复用远程生产URL。
4. 支付/平台客户端在普通自动化测试中用httpx边界替身，不调用正式渠道；test/live开关同时核验商户、appid与回调环境，test模式不能加载生产签名凭证。
5. 私有COS用测试桶/隔离前缀，PDF和图均为虚构样本；没有真实测试存储时测试模拟边界，生产路径不能缺凭据自动放行。
6. [内部资料例外](governance-proposal.md)已获批准并实现；合成测试可显式配置开关、留存引用和告知版本。默认及生产运行保持关闭，直至真实引用和经审阅告知版本完成配置；不得把买家原文发送给第三方。
7. 生产启动显式禁用自动create_all，所有新增结构由迁移管理；不得用启动应用试探生产数据库当前schema。

## 3. 后续测试命令（文件实现后执行）

所有命令从指定目录运行，使用项目现有虚拟环境；新增业务测试多数仍待实现，已运行的工具测试与旧回归逐项记入实施记录，不据此声称整个商城测试通过。

### 统一自动化入口（T005已完成并在真实MySQL验证）

```bash
cd '/Users/leelee/Desktop/北京鲁泰微信小程序项目/LuTaiMiniProgram'
bash scripts/test-mall.sh
```

该入口在Python、Node及Docker等项目运行工具可用后，一次完成锁定依赖检查/必要安装、启动本轮专属MySQL测试容器、等待健康、迁移与fixtures、后端新功能/兼容回归及前端自动化，再清理。可复用本轮容器内验证过的fixture，不能要求用户先手工建库或输入生产连接。单条入口验证自动化套件，不替代参考图确认、真机、5人体验或真实平台联调。

T005已创建`backend/docker-compose.mall-test.yml`及runner隔离单元测试，并已在真实MySQL 8/TLS通过。它自动兼容`docker compose`或独立`docker-compose`，不修改用户Docker配置；使用随机运行标识、临时端口和`bjrutai_mall_test_`库前缀，生成本轮专属凭据及连接配置，应用TLS测试配置，不读生产.env或商户密钥。fixture核验host、库名前缀及本轮资源所有权标识，错目标在DDL前拒绝；清理仅限本轮容器/卷，失败保持原非零状态。空测试库先导入不可变legacy023空结构基线，再真实迁移到026；不声称重放001–023，详见实施记录。CI使用同一入口。下方分项命令用于定位失败，不再要求人工建库。

### 后端：契约、规则及故障恢复

```bash
cd '/Users/leelee/Desktop/北京鲁泰微信小程序项目/LuTaiMiniProgram/backend'
.venv/bin/python -m pytest tests/contract/test_mall_*.py tests/unit/test_mall_*.py tests/unit/test_performance_adjustments.py tests/integration/test_mall_*.py -q
```

测试外部模式强制test；普通套件不得触发真实支付、退款、发货或开票。测试用依赖注入隔离新任务，不能在import时启动实际出站worker。旧SQLite套件继续覆盖基本契约，不作为并发证明。

### 后端：真实MySQL并发与迁移

```bash
cd '/Users/leelee/Desktop/北京鲁泰微信小程序项目/LuTaiMiniProgram/backend'
bash ../scripts/test-mall.sh --backend-mysql
```

分项入口同样自动准备和清理专属库，不要求人工预置；fixture必须拒绝非本轮容器及库。覆盖两独立会话/worker，不在同会话串行假装并发。迁移已从legacy023基线真实执行到029，并验证表/索引/外键/约束、同意场景枚举、关闭申请附加列及`029→023→029`回环；空库不生造历史冻结快照。028存在关闭申请事实时拒绝有损降级；成功降级仅对空测试库验收，线上有交易不drop表。

### 后端：原功能回归

```bash
cd '/Users/leelee/Desktop/北京鲁泰微信小程序项目/LuTaiMiniProgram/backend'
.venv/bin/python -m pytest tests/unit/test_consumption_service.py tests/unit/test_commission_service.py tests/unit/test_commission_freeze.py tests/unit/test_settlement_service.py tests/contract/test_admin_performance.py tests/contract/test_personal_performance_rules.py tests/contract/test_performance_points.py tests/integration/test_performance_settlement_flow.py -q
```

实施切片通过后再运行完整后端套件，明确区分既有失败与本次回归，不为文档改动重复运行生产相关服务。

### 管理后台

```bash
cd '/Users/leelee/Desktop/北京鲁泰微信小程序项目/LuTaiMiniProgram/manageSystem'
npx vitest run
npm run build
```

复用已锁依赖；只有缺依赖才按锁文件安装，不因规划升级主版本。重点测菜单权限、状态动作、重复提交、净可核销、发票领取及对账差异。灰度中的条件性原文动作默认不出按钮/不可用，接口仍独立拒绝。

### 小程序服务与后续页面

```bash
cd '/Users/leelee/Desktop/北京鲁泰微信小程序项目/LuTaiMiniProgram/miniProgram'
node --test tests/unit/*.test.js tests/contract/*.test.js tests/integration/*.test.js
```

使用支持node:test的Node18+。可先实现服务契约及状态转换测试；缺本轮风格参考图不得据此先做视觉页面。参考图到位后再检查开发者工具及iOS/Android真机：安全区域、键盘、输入错误、加载/空/失败/无权、支付取消/未知、私有PDF取票和返回原单。

## 4. 必测故障与兼容场景

| 组 | 场景 | 必须观测到 |
|---|---|---|
| T01 请求 | 同key同body、异body、重启、多worker、旧权限重放 | 原结果或409；实时拒权；无重复订单 |
| T02 库存 | 最后1件100请求；多SKU按反序购买；关单与支付并发 | 无负可售、无死锁未处理、无先回库再确认支付 |
| T03 外部未知 | 下单/退款网络调用前后崩溃，实际渠道成功响应丢失 | 稳定外部身份，重启先查原号，无多付多退 |
| T04 通知 | 验签失败、重放、错主体金额、落库成功响应前崩溃 | 无效非成功；有效持久提交后ACK；重复无二次影响 |
| T05 任务 | 两worker争领、租约过期、旧版本迟到、处理完提交前崩溃 | 去重和版本保护；业务效果唯一；人工待办有责任 |
| T06 售后 | 发货与审核竞争、额度并发、ABNORMAL、损坏实物、超窗口 | 不超退不误回库；资金未知占用；明确人工处理 |
| T07 来源 | 商城独有月、仅调整月、跨来源全局明细、客户无归属 | 可核算/可处理、总明细一致、不造伪客户 |
| T08 冻结 | 收款退款与月审核并发；改规则转组织；原期无结果行后补归属；缺证据 | 输入旧则409；原范围原规则重放；证据锚点支持原结果NULL，不补冻结行；不足人工核实 |
| T09 舍入时间 | 半分/大金额/阶梯边界；UTC/BJT月末；迟到支付 | 兼容legacy算法；新商城按BJ归期，旧冻结/旧Bill期间不搬迁 |
| T10 兑现 | 原期已核销后退款；未来100抵债480；应用与核销并发 | 原核销不改，未来可兑0债380，不绕过或双扣；正向补差可兑现有来源 |
| T11 发票 | 重复领取、实际出票本地未知、退款先于回传、部分冲/全冲重开 | 真实出票不丢、无重复有效覆盖，资金与票据状态分开 |
| T12 文件 | 伪造owner、MIME、checksum、缺凭据、跨买家、链接过期 | 拒绝；同票补交不重开；无永久私有URL |
| T13 平台 | 发货上传失败重试、运单改后旧任务、平台确认延迟 | 不重复出库、不覆盖新运单，本地收货不等于平台资金解冻 |
| T14 原功能 | 登录绑定、医院同步、手工消费、文章、个人覆盖、核销及导出 | 旧无商城样本保持原值原行为，历史已确认走冻结 |

SC-002用户测试、SC-003规模查询、SC-004并发必须保存真实耗时及数量，不用理论复杂度替代实测。

## 5. 外部平台联调与开放购买

G-PROTOCOL宪章3.0.0限定例外已采纳且官方协议已核验；T048本地实现和隔离回归已完成。真实回调地址注册/部署仍受G-LIVE与具体授权约束。第一期微信发货信息由员工在小程序后台手工录入，不实现发货API；T054已记录官方方式与状态边界，T056已实现商城内的人工登记回填，T131核验真实账号入口/权限。

只在获准的测试/受控条件下核验商户号和小程序关联、微信支付权限、HTTPS通知、公钥/证书轮换、发货管理适用条件和真实字段。核验收款、查单、关单、退款受理及到账；平台字段文档暂不可读时不猜参数并投产。真实资金操作需在具体金额和对象明确的业务授权下执行，本指南不构成批量真实退款授权。开售前逐项完成[T131平台预检](platform-acceptance.md)和[T133发布准备核对](release-readiness.md)；运行开关应按[发布/回退手册](rollout-runbook.md)核验，不能用单一前端开关替代运行配置与数据库购买状态。

财务确认实际销售/开票主体、商品税目税率及其人工开票流程；工作人员上传并确认后，商城按其确认登记有效，不连接税务平台验真或自行生成发票。使用测试PDF核对私有ACL及同单访问；生产桶权限仍须由T131实际验证。

开关按“新购关闭→迁移与兼容部署→隔离验证→经营/规则/平台/资料规范齐备→灰度→新购开放”。上线后监测支付确认延迟、退款未知及异常、任务积压、微信后台人工登记待办、快递100物流进度、待开红冲、绩效差额结余与对账差异。

## 6. 回退

回退顺序、双层关闭验证、外部出站与worker的独立影响、任务积压监控及存量订单/售后保护见[发布/回退手册](rollout-runbook.md)。任何退款、支付、发票或资金事实不能通过数据库回滚撤回；生产不得降级迁移、删除未知请求或清空已接受工作项。

## 7. UI提醒位置

用户已提供商品列表布局参考图，要求借鉴搜索/筛选和双列商品卡片，不显示“综合”tab，并由实现方确定视觉风格。已在[ui-reference.md](ui-reference.md)记录暖灰米底、松针绿交互、陶土红价格的实现约定。用户于2026-11-10确认T132真机验收完成；设备版本、逐项结果及5人计时原始记录未归档，详见[device-acceptance.md](device-acceptance.md)。

## 8. 快递100专项（后续执行）

用户已开通服务，账户产品权益、额度及凭据仍在实施时核验；普通自动化只fake接口，不查询真实买家运单。协议与资料边界见[物流补充](logistics-integration.md)，任务T057–T061，验收AC-046–051。

实现后执行以下新增测试（此刻文件尚未创建）：

```bash
cd '/Users/leelee/Desktop/北京鲁泰微信小程序项目/LuTaiMiniProgram/backend'
.venv/bin/python -m pytest tests/unit/test_kuaidi100_client.py tests/contract/test_mall_logistics.py tests/integration/test_mall_logistics_flow.py -q
```

按第2节隔离MySQL前提另执行`tests/mysql/test_mall_logistics_cache.py`，用可控时钟和两个数据库会话验证同运单跨买家/后台共享缓存、至少30分钟频率、单次占用、失败退避及旧运单响应隔离；不能只测单进程内缓存。覆盖精确param签名、空轨迹/预计值、电话校验失败、额度不足、超时和旧轨迹陈旧标识，敏感字段不进日志。物流签收不得自动执行退款、退货入库、绩效变更、微信确认或资金解冻。地图页面等参考图及实际安全域名条件核验后另行落实。

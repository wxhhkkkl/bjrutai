# Tasks: 小程序文章分类筛选

- [x] T001 [US1] 在 `backend/src/api/v1/articles.py` 增加公开文章分类清单接口，并在 `backend/tests/contract/test_articles.py` 验证无需认证的返回内容。
- [x] T002 [US1] 在 `miniProgram/services/article-service.js` 与 `miniProgram/models/article.js` 实现分类清单和分类参数适配，并补充契约测试。
- [x] T003 [US1] 在 `miniProgram/pages/articles/index.*` 增加分类选择、切换重载、分页保持及分类接口失败降级，并补充阅读流程测试。
- [x] T004 [US1] 运行后端文章接口和小程序文章阅读相关测试。

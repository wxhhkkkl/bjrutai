# Implementation Plan: 小程序文章分类筛选

**Branch**: `feature/user-feedback-20260914` | **Date**: 2026-09-14 | **Spec**: [spec.md](./spec.md)

## Summary

为文章资讯页补充横向分类筛选栏。后端在现有公开文章路由中增加只读分类清单；小程序独立加载该清单，并把所选分类透传给既有文章列表及其分页请求。

## Constitution Check

- 规格先行：通过；筛选、降级、空态和并发场景已在规格中记录。
- UI：通过；使用原生 WXML/WXSS 横向滚动控件，不新增依赖。
- 隐私：通过；公开分类接口只返回编号、名称和排序信息。
- 韧性：通过；分类失败只降级为“全部”，不影响文章列表。
- 测试：通过；补充公开接口、服务请求和列表切换测试。

## Files

- `backend/src/api/v1/articles.py`
- `backend/tests/contract/test_articles.py`
- `miniProgram/services/article-service.js`
- `miniProgram/models/article.js`
- `miniProgram/pages/articles/index.js`
- `miniProgram/pages/articles/index.wxml`
- `miniProgram/pages/articles/index.wxss`
- `miniProgram/tests/contract/article-api-contract.test.js`
- `miniProgram/tests/integration/article-reading-flow.test.js`

# Implementation Plan: 我的推广码闭环完善

**Branch**: `015-promotion-code-completion` | **Date**: 2026-08-10 | **Spec**: `spec.md`

## Summary

统一后端推广码响应和小程序消费字段；将页面请求改为顺序加载；实现微信相册保存；拒绝缺少有效令牌的同步自动归属；接通已存在但被页面拦截的客户和资料接口。

## Constitution Check

- 规格先行：通过；本功能的场景、外部依赖和受控失败状态已记录。
- 外部依赖：哈尔滨儒泰负责实际二维码生成与扫码回传，仓库内不虚构其 API。
- 隐私：不记录或显示客户敏感信息；令牌只用于已授权的推广归属。
- 测试：为字段适配、分享路径和无令牌同步补充自动化覆盖。

## Files

- `backend/src/services/promotion_service.py`
- `backend/src/services/sync_service.py`
- `miniProgram/pages/promotion-code/index.js`
- `miniProgram/pages/promotion-code/index.wxml`
- `miniProgram/models/promotion-code.js`
- `miniProgram/pages/customer-detail/index.js`
- `miniProgram/pages/followup-record/index.js`
- `miniProgram/pages/binding-records/index.js`
- `miniProgram/pages/auth/profile-setup/index.js`
- 推广码相关单元与契约测试

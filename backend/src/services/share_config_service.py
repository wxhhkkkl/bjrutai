"""Read and manage share configs for registered Mini Program pages."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.exceptions import BadRequestException, ConflictException, NotFoundException
from ..models.share_config import MiniProgramShareConfig

DEFAULT_CONFIGS = (
    {
        "page_key": "home",
        "page_name": "首页",
        "friend_title": "儒泰医联｜让健康知识，走进日常",
        "friend_image_url": "/assets/images/home-share-friend-v1.jpg",
        "timeline_title": "儒泰医联｜让健康知识，走进日常",
        "timeline_image_url": "/assets/images/home-share-timeline-v1.jpg",
        "landing_path": "/pages/home/index",
    },
    {
        "page_key": "promotion-code",
        "page_name": "客户绑定码",
        "friend_title": "儒泰医联｜您的专属健康服务入口",
        "friend_image_url": "/assets/images/promotion-share-friend-v1.jpg",
        "timeline_title": None,
        "timeline_image_url": None,
        "landing_path": "/pages/patient-binding/index?refToken={refToken}",
    },
)

# This catalogue mirrors miniProgram/app.json. Keep both source and landing
# options tied to the routes currently registered by the Mini Program.
MINI_PROGRAM_ROUTES = (
    ("/pages/home/index", "首页"),
    ("/pages/customers/index", "客户"),
    ("/pages/internet-hospital/index", "互联网医院"),
    ("/pages/mall/index", "商城"),
    ("/pages/customer-detail/index", "客户详情"),
    ("/pages/customer-edit/index", "编辑客户"),
    ("/pages/followup-record/index", "跟进记录"),
    ("/pages/customer-analysis/index", "客户分析"),
    ("/pages/contribution/index", "消费记录"),
    ("/pages/contribution-detail/index", "消费详情"),
    ("/pages/articles/index", "文章列表"),
    ("/pages/article-detail/index", "文章详情"),
    ("/pages/profile/index", "我的"),
    ("/pages/account-profile/index", "账户信息"),
    ("/pages/help-feedback/index", "帮助与反馈"),
    ("/pages/notifications/index", "消息通知"),
    ("/pages/privacy-authorization/index", "隐私授权"),
    ("/pages/legal-document/index", "法律文档"),
    ("/pages/promotion-code/index", "客户绑定码"),
    ("/pages/patient-binding/index", "客户绑定"),
    ("/pages/staff-invite/index", "员工邀请"),
    ("/pages/staff-join/index", "加入组织"),
    ("/pages/customer-binding/index", "客户绑定结果"),
    ("/pages/binding-records/index", "绑定记录"),
    ("/pages/binding-result/index", "绑定结果"),
    ("/pages/auth/login/index", "登录"),
    ("/pages/auth/profile-setup/index", "完善资料"),
    ("/pages/auth/bind-wechat/index", "绑定微信"),
    ("/pages/org-performance/index", "组织业绩"),
    ("/pages/performance/index", "个人业绩"),
    ("/pages/common/feature-placeholder/index", "功能占位页"),
    ("/pages/index/index", "入口页"),
)

SHARE_SOURCE_EXCLUDED_ROUTES = frozenset({
    "/pages/help-feedback/index",
    "/pages/notifications/index",
    "/pages/privacy-authorization/index",
    "/pages/legal-document/index",
    "/pages/patient-binding/index",
    "/pages/staff-invite/index",
    "/pages/staff-join/index",
    "/pages/customer-binding/index",
    "/pages/account-profile/index",
    "/pages/binding-records/index",
    "/pages/binding-result/index",
    "/pages/auth/login/index",
    "/pages/auth/profile-setup/index",
    "/pages/auth/bind-wechat/index",
    "/pages/org-performance/index",
})
SHARE_SOURCE_ROUTES = tuple(
    route for route in MINI_PROGRAM_ROUTES if route[0] not in SHARE_SOURCE_EXCLUDED_ROUTES
)

def page_key_for_route(route: str) -> str:
    if route == "/pages/home/index":
        return "home"
    if route == "/pages/promotion-code/index":
        return "promotion-code"
    return route.strip("/").replace("/", "_")


_ROUTE_BY_KEY = {page_key_for_route(path): (path, name) for path, name in MINI_PROGRAM_ROUTES}
_SHARE_SOURCE_BY_KEY = {
    page_key_for_route(path): (path, name) for path, name in SHARE_SOURCE_ROUTES
}

_DEFAULT_BY_KEY = {item["page_key"]: item for item in DEFAULT_CONFIGS}


def _expected_landing_path(page_key: str) -> str:
    default = _DEFAULT_BY_KEY.get(page_key)
    if default is not None:
        return default["landing_path"]
    route = _SHARE_SOURCE_BY_KEY.get(page_key) or _ROUTE_BY_KEY.get(page_key)
    if route is None:
        raise NotFoundException(message="分享配置不存在")
    return route[0]


def _serialize(item: MiniProgramShareConfig) -> dict:
    source_route, _source_name = _ROUTE_BY_KEY[item.page_key]
    return {
        "pageKey": item.page_key,
        "pageName": item.page_name,
        "sourcePath": source_route,
        "friendTitle": item.friend_title,
        "friendImageUrl": item.friend_image_url,
        "timelineTitle": item.timeline_title,
        "timelineImageUrl": item.timeline_image_url,
        "landingPath": _expected_landing_path(item.page_key),
        "version": item.version,
        "updatedAt": item.updated_at.isoformat() if item.updated_at else None,
        "channels": ["friend", "timeline"] if item.page_key == "home" else ["friend"],
    }


def _serialize_default(item: dict) -> dict:
    source_route, _source_name = _ROUTE_BY_KEY[item["page_key"]]
    return {
        "pageKey": item["page_key"],
        "pageName": item["page_name"],
        "sourcePath": source_route,
        "friendTitle": item["friend_title"],
        "friendImageUrl": item["friend_image_url"],
        "timelineTitle": item["timeline_title"],
        "timelineImageUrl": item["timeline_image_url"],
        "landingPath": item["landing_path"],
        "version": 1,
        "updatedAt": None,
        "channels": ["friend", "timeline"] if item["page_key"] == "home" else ["friend"],
    }


async def seed_share_configs(db: AsyncSession) -> None:
    """Defaults are inserted by migration 024; keep administrator deletions persistent."""
    return None


async def list_share_configs(db: AsyncSession) -> list[dict]:
    result = await db.execute(
        select(MiniProgramShareConfig)
        .order_by(MiniProgramShareConfig.id.asc())
    )
    by_key = {item.page_key: item for item in result.scalars().all()}
    return [_serialize(item) for key, item in by_key.items() if key in _ROUTE_BY_KEY]


async def create_share_config(db: AsyncSession, payload: dict) -> dict:
    page_key = str(payload.get("page_key") or "").strip()
    route = _SHARE_SOURCE_BY_KEY.get(page_key)
    if route is None:
        raise BadRequestException(message="请选择当前小程序已注册的页面")
    existing = await db.execute(
        select(MiniProgramShareConfig).where(MiniProgramShareConfig.page_key == page_key)
    )
    item = existing.scalars().first()
    if item is not None:
        raise ConflictException(message="该页面已存在分享配置")
    landing_path = _validate_path(page_key, payload.get("landing_path") or "/pages/home/index")
    friend_title = str(payload.get("friend_title") or "").strip()
    friend_image_url = _validate_image(payload.get("friend_image_url"), "好友卡片图片")
    if not friend_title:
        raise BadRequestException(message="分享标题不能为空")
    timeline_title = None
    timeline_image_url = None
    if page_key == "home":
        timeline_title = str(payload.get("timeline_title") or "").strip()
        if not timeline_title:
            raise BadRequestException(message="朋友圈分享标题不能为空")
        timeline_image_url = _validate_image(payload.get("timeline_image_url"), "朋友圈卡片图片")
    item = MiniProgramShareConfig(
        page_key=page_key,
        page_name=route[1],
        friend_title=friend_title,
        friend_image_url=friend_image_url,
        timeline_title=timeline_title,
        timeline_image_url=timeline_image_url,
        landing_path=landing_path,
        version=1,
    )
    db.add(item)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictException(message="该页面已存在分享配置，请刷新后重试") from exc
    await db.refresh(item)
    return _serialize(item)


async def get_public_share_config(db: AsyncSession, page_key: str) -> dict:
    if page_key not in _ROUTE_BY_KEY:
        raise NotFoundException(message="分享配置不存在")
    result = await db.execute(
        select(MiniProgramShareConfig).where(MiniProgramShareConfig.page_key == page_key)
    )
    item = result.scalars().first()
    if item is None:
        if page_key in _DEFAULT_BY_KEY:
            return _serialize_default(_DEFAULT_BY_KEY[page_key])
        source_path, page_name = _ROUTE_BY_KEY[page_key]
        return {
            "pageKey": page_key,
            "pageName": page_name,
            "sourcePath": source_path,
            "friendTitle": None,
            "friendImageUrl": None,
            "timelineTitle": None,
            "timelineImageUrl": None,
            "landingPath": source_path,
            "version": 1,
            "updatedAt": None,
            "channels": ["friend"],
        }
    return _serialize(item)


def _validate_image(value: str, label: str) -> str:
    image = str(value or "").strip()
    if not image:
        raise BadRequestException(message=f"{label}不能为空")
    if image.startswith("/") or image.startswith("https://") or image.startswith("http://"):
        return image
    raise BadRequestException(message=f"{label}需使用小程序本地路径或 HTTP(S) 地址")


def _validate_path(page_key: str, path_value: str) -> str:
    path = str(path_value or "").strip()
    expected_path = _expected_landing_path(page_key)
    if path != expected_path:
        raise BadRequestException(message="分享落地页会自动跟随所选页面")
    return expected_path


async def update_share_config(db: AsyncSession, page_key: str, payload: dict) -> dict:
    if page_key not in _ROUTE_BY_KEY:
        raise NotFoundException(message="分享配置不存在")
    result = await db.execute(
        select(MiniProgramShareConfig).where(MiniProgramShareConfig.page_key == page_key)
    )
    item = result.scalars().first()
    if item is None:
        raise NotFoundException(message="分享配置不存在")
    if item.version != payload["version"]:
        raise ConflictException(message="分享配置已被其他管理员修改，请刷新后重试")
    item.friend_title = payload["friend_title"].strip()
    item.friend_image_url = _validate_image(payload["friend_image_url"], "好友卡片图片")
    item.landing_path = _validate_path(page_key, payload["landing_path"])
    if page_key == "home":
        item.timeline_title = payload["timeline_title"].strip()
        item.timeline_image_url = _validate_image(payload["timeline_image_url"], "朋友圈卡片图片")
    else:
        item.timeline_title = None
        item.timeline_image_url = None
    if not item.friend_title or (page_key == "home" and not item.timeline_title):
        raise BadRequestException(message="分享标题不能为空")
    item.version += 1
    await db.commit()
    await db.refresh(item)
    return _serialize(item)


async def delete_share_config(db: AsyncSession, page_key: str, version: int) -> dict:
    if page_key not in _ROUTE_BY_KEY:
        raise NotFoundException(message="分享配置不存在")
    result = await db.execute(
        select(MiniProgramShareConfig).where(MiniProgramShareConfig.page_key == page_key)
    )
    item = result.scalars().first()
    if item is None:
        raise NotFoundException(message="分享配置不存在或已删除")
    if item.version != version:
        raise ConflictException(message="分享配置已被其他管理员修改，请刷新后重试")
    await db.delete(item)
    await db.commit()
    return {"pageKey": page_key, "deleted": True}

"""Business rules and serializers for homepage banners."""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.exceptions import BadRequestException, ConflictException, NotFoundException
from ..models.banner import Banner, BannerActionType, BannerStatus
from ..schemas.banner import BannerCreate, BannerUpdate


STATUS_LABELS = {
    BannerStatus.ENABLED: "已启用",
    BannerStatus.DISABLED: "已停用",
}


async def list_public(db: AsyncSession) -> list[dict]:
    result = await db.execute(
        select(Banner)
        .where(Banner.status == BannerStatus.ENABLED)
        .order_by(Banner.sort_order.asc(), Banner.id.desc())
    )
    return [_to_public_item(item) for item in result.scalars().all()]


async def list_admin(db: AsyncSession, status: str | None = None) -> list[dict]:
    stmt = select(Banner)
    if status:
        try:
            stmt = stmt.where(Banner.status == BannerStatus(status))
        except ValueError as exc:
            raise BadRequestException(message="无效的轮播图状态") from exc
    result = await db.execute(stmt.order_by(Banner.sort_order.asc(), Banner.id.desc()))
    return [_to_admin_item(item) for item in result.scalars().all()]


async def get_banner(db: AsyncSession, banner_id: int) -> Banner:
    result = await db.execute(select(Banner).where(Banner.id == banner_id))
    banner = result.scalar_one_or_none()
    if banner is None:
        raise NotFoundException(message="轮播图不存在")
    return banner


async def create_banner(db: AsyncSession, data: BannerCreate) -> Banner:
    banner = Banner(
        title=_clean_title(data.title),
        image_url=data.imageUrl,
        action_type=BannerActionType(data.actionType),
        article_id=data.articleId if data.actionType == BannerActionType.ARTICLE.value else None,
        sort_order=data.sortOrder,
        status=BannerStatus.DISABLED,
        version=1,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(banner)
    await db.flush()
    await db.refresh(banner)
    return banner


async def update_banner(db: AsyncSession, banner_id: int, data: BannerUpdate) -> Banner:
    banner = await get_banner(db, banner_id)
    if data.version != banner.version:
        raise ConflictException(
            message="轮播图已被其他管理员修改，请刷新后重试",
            detail={"currentVersion": banner.version, "providedVersion": data.version},
        )

    values = data.model_dump(exclude_unset=True)
    values.pop("version", None)
    if "title" in values:
        banner.title = _clean_title(values["title"])
    if "imageUrl" in values:
        banner.image_url = values["imageUrl"]
    if "sortOrder" in values:
        banner.sort_order = values["sortOrder"]
    if "actionType" in values:
        banner.action_type = BannerActionType(values["actionType"])
    if "articleId" in values:
        banner.article_id = values["articleId"]

    if banner.action_type == BannerActionType.ARTICLE and banner.article_id is None:
        raise BadRequestException(message="跳转文章时必须选择文章")
    if banner.action_type == BannerActionType.NONE:
        banner.article_id = None

    banner.version += 1
    banner.updated_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(banner)
    return banner


async def set_status(db: AsyncSession, banner_id: int, status: BannerStatus) -> Banner:
    banner = await get_banner(db, banner_id)
    if banner.status == status:
        raise BadRequestException(message=f"轮播图已{STATUS_LABELS[status]}")
    banner.status = status
    banner.version += 1
    banner.updated_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(banner)
    return banner


async def delete_banner(db: AsyncSession, banner_id: int) -> None:
    banner = await get_banner(db, banner_id)
    await db.delete(banner)
    await db.flush()


def _clean_title(value: str | None) -> str | None:
    text = str(value or "").strip()
    return text or None


def _to_public_item(banner: Banner) -> dict:
    return {
        "bannerId": str(banner.id),
        "title": banner.title,
        "imageUrl": banner.image_url,
        "actionType": banner.action_type.value,
        "articleId": str(banner.article_id) if banner.article_id else None,
        "sortOrder": banner.sort_order,
    }


def _to_admin_item(banner: Banner) -> dict:
    return {
        **_to_public_item(banner),
        "status": banner.status.value,
        "statusLabel": STATUS_LABELS[banner.status],
        "createdAt": banner.created_at.isoformat() if banner.created_at else None,
        "updatedAt": banner.updated_at.isoformat() if banner.updated_at else None,
        "version": banner.version,
    }

"""Private file admin endpoints use live permissions."""

from ...api.mall_deps import require_mall_admin
from .mall_files import build_file_router

router = build_file_router(
    "/admin/mall/files",
    None,
    require_mall_admin("mall.files.write"),
    require_mall_admin("mall.files.read"),
    admin=True,
)

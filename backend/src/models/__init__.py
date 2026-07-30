# Import all models so Alembic can discover them for autogenerate.
# Order matters for FK resolution – import leaf/parent models first.

from ..core.database import Base  # noqa: F401

from .user import AdminAccount, User, admin_account_roles  # noqa: F401
from .role import Role  # noqa: F401
from .hierarchy import HierarchyNode, Promoter, hierarchy_snapshots  # noqa: F401
from .qualification import Qualification  # noqa: F401
from .binding import BindingChangeLog, BindingRequest, Customer  # noqa: F401
from .promotion import PromotionCode  # noqa: F401
from .bill import Bill  # noqa: F401
from .contribution import ContributionRecord, SettlementLog  # noqa: F401
from .sharing import ContributionCoefficient, SharingRule, sharing_rule_change_logs  # noqa: F401
from .article import Article  # noqa: F401
from .followup import FollowupRecord  # noqa: F401
from .consent import Agreement, ConsentRecord  # noqa: F401
from .notification import Notification  # noqa: F401
from .audit import ApiCallLog, AuditLog  # noqa: F401
from .idempotency import IdempotencyKey  # noqa: F401
from .session import UserToken  # noqa: F401
from .report import Report  # noqa: F401

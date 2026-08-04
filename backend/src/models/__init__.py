# Import all models so Alembic can discover them for autogenerate.
# Order matters for FK resolution – import leaf/parent models first.

from ..core.database import Base  # noqa: F401

from .user import AdminAccount, User, admin_account_roles  # noqa: F401
from .role import Role  # noqa: F401
from .organization import Organization, OrgStatus  # noqa: F401
from .distributor import Distributor, DistributorStatus, OrgRole  # noqa: F401
from .org_qualification import OrganizationQualification, OrgQualStatus  # noqa: F401
from .org_history import OrgHistory, OrgHistoryAction  # noqa: F401
# 废弃模型（表已迁移重命名，映射 _deprecated_*）保留注册，兼容旧数据查询与测试
from .hierarchy import HierarchyNode, Promoter, hierarchy_snapshots  # noqa: F401
from .qualification import Qualification  # noqa: F401
from .binding import BindingChangeLog, BindingRequest, Customer  # noqa: F401
from .customer_change_log import ChangeOperationType, CustomerChangeLog  # noqa: F401
from .performance_rule import PerformanceRule, PerformanceRuleChangeLog, RuleStatus, RuleType  # noqa: F401
from .commission_result import CommissionResult  # noqa: F401
from .promotion import PromotionCode  # noqa: F401
from .bill import Bill  # noqa: F401
from .contribution import ContributionRecord, SettlementLog  # noqa: F401
from .sharing import ContributionCoefficient, SharingRule, sharing_rule_change_logs  # noqa: F401
from .category import ArticleCategory  # noqa: F401
from .article import Article  # noqa: F401
from .followup import FollowupRecord  # noqa: F401
from .consent import Agreement, ConsentRecord  # noqa: F401
from .notification import Notification  # noqa: F401
from .audit import ApiCallLog, AuditLog  # noqa: F401
from .idempotency import IdempotencyKey  # noqa: F401
from .session import UserToken  # noqa: F401
from .report import Report  # noqa: F401

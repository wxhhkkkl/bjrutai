"""drop contribution_records; synthesize legacy bills (去掉业绩贡献值)

Revision ID: 012
Revises: 011
Create Date: 2026-08-05

去掉「业绩贡献值」体系：
1. 存量 contribution_records 中无账单的手工/团队记录（bill_id IS NULL 且 points>0）
   按数值生成合成账单（消费金额，单位分），保证如「测试分销」150 等历史数据
   在业绩贡献=消费金额的新口径下仍可见。
2. 删除 contribution_records / settlement_logs / contribution_coefficient 三表。

破坏性迁移：原贡献记录行不可恢复（downgrade 仅重建空表并清理合成数据），
升级前请备份数据库。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '012'
down_revision: Union[str, None] = '011'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # ── 1) 合成账单：无账单且贡献值>0 的手工/团队记录 → 消费金额账单 ──
    rows = bind.execute(sa.text(
        """
        SELECT cr.id, cr.distributor_id, cr.customer_id, cr.occurred_at,
               CAST(cr.points AS DECIMAL(20,2)) AS pts
        FROM contribution_records cr
        WHERE cr.bill_id IS NULL
          AND cr.status NOT IN ('REVERSED', 'CANCELLED')
          AND CAST(cr.points AS DECIMAL(20,2)) > 0
        """
    )).fetchall()

    # 分销员 → 合成客户 id（惰性创建，按分销员去重）
    synth_cust: dict[int, int] = {}

    def _resolve_customer(cust_id) -> Union[int, None]:
        if cust_id and cust_id > 0:
            exists = bind.execute(
                sa.text("SELECT id FROM customers WHERE id = :c"), {"c": cust_id}
            ).first()
            if exists:
                return cust_id
        return None

    for rec_id, dist_id, cust_id, occurred_at, pts in rows:
        cid = _resolve_customer(cust_id)
        if cid is None:
            if dist_id not in synth_cust:
                bind.execute(
                    sa.text(
                        """
                        INSERT INTO customers
                          (distributor_id, name, binding_status, rutai_user_id,
                           version, created_at, updated_at)
                        VALUES (:d, '历史消费', 'BOUND', :ruid, 1, NOW(), NOW())
                        """
                    ),
                    {"d": dist_id, "ruid": f"legacy-cust-{dist_id}"},
                )
                cid = int(bind.execute(sa.text("SELECT LAST_INSERT_ID()")).scalar())
                synth_cust[dist_id] = cid
            else:
                cid = synth_cust[dist_id]

        cents = int(round(float(pts) * 100))
        bind.execute(
            sa.text(
                """
                INSERT INTO bills
                  (customer_id, rutai_user_id, transaction_id, transaction_time,
                   consultation_fee_cent, medicine_fee_cent, total_amount_cent,
                   discount_amount_cent, paid_amount_cent, refund_amount_cent,
                   transaction_status, created_at, updated_at)
                VALUES
                  (:cid, :ruid, :txid, :tt, 0, 0, :cents, 0, :cents, 0,
                   'PAID', NOW(), NOW())
                ON DUPLICATE KEY UPDATE transaction_id = VALUES(transaction_id)
                """
            ),
            {
                "cid": cid,
                "ruid": f"legacy-cust-{dist_id}",
                "txid": f"legacy-contrib-{rec_id}",
                "tt": occurred_at,
                "cents": cents,
            },
        )

    # ── 2) 删除贡献相关表 ──
    op.drop_table("contribution_coefficient")
    op.drop_table("settlement_logs")
    op.drop_table("contribution_records")


def downgrade() -> None:
    # 清理合成数据
    op.get_bind().execute(sa.text("DELETE FROM bills WHERE transaction_id LIKE 'legacy-contrib-%'"))
    op.get_bind().execute(sa.text("DELETE FROM customers WHERE rutai_user_id LIKE 'legacy-cust-%'"))

    # 尽力重建三表（原始贡献行不可恢复）
    op.create_table(
        "contribution_coefficient",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("coefficient", sa.String(length=20), nullable=False),
        sa.Column("effective_from", sa.DateTime(), nullable=False),
        sa.Column("previous_coefficient", sa.String(length=20), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "settlement_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("period", sa.String(length=7), nullable=False),
        sa.Column("status", sa.Enum("running", "completed", "failed", name="settlement_status_enum"), nullable=False),
        sa.Column("total_records", sa.Integer(), nullable=False),
        sa.Column("settled_records", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )
    op.create_table(
        "contribution_records",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("distributor_id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("bill_id", sa.Integer(), nullable=True),
        sa.Column("points", sa.String(length=20), nullable=False),
        sa.Column("status", sa.Enum("pending", "confirmed", "settled", "reversed", "cancelled", name="contribution_status_enum"), nullable=False),
        sa.Column("category", sa.Enum("binding", "service", "followup", "bill", "adjustment", name="contribution_category_enum"), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("source_type", sa.String(length=50), nullable=True),
        sa.Column("source_id", sa.String(length=100), nullable=True),
        sa.Column("rule_version", sa.String(length=20), nullable=True),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("settled_at", sa.DateTime(), nullable=True),
        sa.Column("reversed_record_id", sa.Integer(), nullable=True),
        sa.Column("adjustment_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

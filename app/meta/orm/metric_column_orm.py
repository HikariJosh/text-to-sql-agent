from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.meta.orm.base import Base


class MetricColumnORM(Base):
    """指标-字段关联表ORM模型，表示指标和列之间的多对多关系
    指标编号和列编号共同组成主键，确保每个指标-列组合唯一
    e.g. metric_id='metric_456', column_id='col_123' 表示指标metric_456关联了列col_123"""

    __tablename__ = "column_metric"

    column_id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="列编号")
    metric_id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="指标编号")

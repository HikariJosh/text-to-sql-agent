from dataclasses import dataclass


@dataclass
class MetricColumn:
    """指标-字段关联实体，表示哪个指标关联了哪个字段，对应meta数据库中的column_metric表"""

    column_id: str  # 字段id，如fact_order.order_amount
    metric_id: str  # 指标id，如销售总额

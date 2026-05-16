from dataclasses import dataclass


@dataclass
class MetricInfo:
    """指标信息实体，对应meta数据库中的metric_info表"""

    id: str  # 指标的唯一标识，一般等于指标名
    name: str  # 指标名，如销售总额
    description: str  # 指标的描述信息
    relevant_columns: list[str]  # 关联的字段id列表，如["orders.price_usd"]
    formula: str  # 计算公式，如 COUNT(DISTINCT website_session_id)
    alias: list[str]  # 指标的别名列表，如["销售额", "总销售额"]

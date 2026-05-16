from dataclasses import dataclass
from typing import Any


@dataclass
class ColumnInfo:
    """对应models中的ColumnInfo，表示字段的元信息"""

    id: str  #  dim_customer_customer_id
    name: str  # customer_id
    type: str  # string, int, float, date等
    role: str  # PrimaryKey, ForeignKey, Measure, Dimension
    examples: list[Any]  # 数据示例，可以是列表或者字典，取决于具体实现
    description: str  # 字段描述信息
    alias: list[str]  # 字段别名列表
    table_id: str  # dim_customer

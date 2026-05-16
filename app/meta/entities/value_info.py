from dataclasses import dataclass


@dataclass
class ValueInfo:
    """字段取值实体，对应ES中的value_index索引"""

    id: str  # 取值的唯一标识，格式为 table.column.value，如dim_region.province.北京市
    value: str  # 取值内容，如"北京市"
    column_id: str  # 所属字段的id，如dim_region.province

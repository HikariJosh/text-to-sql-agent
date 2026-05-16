from dataclasses import dataclass


@dataclass
class TableInfo:
    """表信息实体，对应meta数据库中的table_info表"""

    id: str  # 表的唯一标识，一般等于表名
    name: str  # 表名，如fact_order
    role: str  # 表的角色：fact(事实表)、dim(维度表)
    description: str  # 表的描述信息

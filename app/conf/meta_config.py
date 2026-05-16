"""
业务元数据配置的 schema 定义。
对应 conf/meta_config/ 目录下的 table_column_info.yaml 和 metric_info.yaml

本文件用于定义从配置文件中读取的元数据结构，包括表信息、字段信息和指标信息。这些结构将被用于构建 Meta 知识库，支持后续的查询和分析功能。
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ColumnConfig:
    """字段配置，描述一个字段的元信息和同步策略"""

    name: str  # 字段名
    role: str  # 字段角色：PrimaryKey、ForeignKey、Dimension、Measure
    description: str  # 字段描述
    alias: list[str]  # 字段别名，用于扩大召回
    sync: bool  # 是否需要同步取值到ES(只有维度字段需要)
    # 以下字段为人工参考，不参与构建，仅作为文档备查
    column_id: Optional[str] = None  # 字段编号，如 order_items.order_item_id
    type: Optional[str] = None  # 数据类型，如 bigint unsigned
    examples: Optional[list] = None  # 示例值，如 [1, 2, 3]


@dataclass
class TableConfig:
    """表配置，描述一张表的元信息和包含的字段"""

    name: str  # 表名
    role: str  # 表角色：fact(事实表)、dim(维度表)
    description: str  # 表描述
    columns: list[ColumnConfig]  # 字段列表


@dataclass
class MetricConfig:
    """指标配置，描述一个业务指标"""

    name: str  # 指标名
    description: str  # 指标描述
    relevant_columns: list[str]  # 关联的字段id列表
    formula: str  # 计算公式
    alias: list[str]  # 指标别名
    # 以下字段为人工参考，不参与构建，仅作为文档备查
    metric_id: Optional[str] = None  # 指标编号，如 total_sessions


@dataclass
class MetaConfig:
    """知识库配置的顶层结构"""

    # 用 | None 是因为在构建知识库时，可能只想同步表信息或者指标信息
    tables: list[TableConfig] | None = None
    metrics: list[MetricConfig] | None = None

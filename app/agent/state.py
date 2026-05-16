"""
Agent状态定义：定义了agent图在执行过程中传递的状态数据结构

LangGraph的状态机制：
  - DataAgentState是一个TypedDict，定义了图中所有可能的状态字段
  - 每个节点从state中读取需要的数据，处理后通过return dict写回state
  - 下游节点读取上游节点写入的数据，形成数据流水线
  - 所有字段都是可选的，未赋值时为None

数据流向：
  query → clarify → extract_keywords → [recall_*] → merge → [filter_*]
  → add_extra_context → think → generate_sql → validate_sql
  → execute_sql → summarize
"""

from typing import TypedDict

from app.meta.entities.column_info import ColumnInfo
from app.meta.entities.metric_info import MetricInfo
from app.meta.entities.value_info import ValueInfo


class ColumnInfoState(TypedDict):
    """
    字段信息的状态表示，用于传递给LLM(比entity更精简),缺少id等元信息
    由filter_table节点产出，从ColumnInfo实体精简而来
    """

    name: str  # 字段名，如created_at
    type: str  # 数据类型，如datetime、varchar
    role: str  # 字段角色，如primary_key、foreign_key、dimension、measure
    examples: list  # 示例值，如["2012-01-01", "2012-02-01"]
    description: str  # 字段描述，如"会话创建时间"
    alias: list[str]  # 别名列表，如["创建时间", "订单日期"]


class TableInfoState(TypedDict):
    """
    表信息的状态表示，包含表的基本信息和其下的字段列表,缺少id等元信息
    由filter_table节点产出
    """

    name: str  # 表名，如website_sessions
    role: str  # 表角色：fact(事实表)、dim(维度表)
    description: str  # 表描述，如"网站会话事实表"
    columns: list[ColumnInfoState]  # 该表下的字段列表


class MetricInfoState(TypedDict):
    """
    指标信息的状态表示,缺少id等元信息
    由filter_metric节点产出，用于指导LLM理解业务指标的计算方式
    """

    name: str  # 指标名，如"会话数"
    description: str  # 指标定义和计算方式
    relevant_columns: list[str]  # 相关字段，如["website_sessions.website_session_id"]
    alias: list[str]  # 别名，如["sessions", "访问数"]


class DateInfoState(TypedDict):
    """
    日期上下文信息，帮助LLM理解时间相关的问题
    由add_extra_context节点产出
    关键：date取自数据表的最新时间(MAX(created_at))，而非系统当前时间
    """

    date: str  # 数据最新日期，如2015-03-19（非系统时间）
    weekday: str  # 星期几，如Thursday
    quarter: str  # 季度，如Q1


class DBInfoState(TypedDict):
    """
    数据库环境信息，帮助LLM生成正确的SQL语法
    由add_extra_context节点通过dw_repository.get_db_info()获取
    不同数据库的SQL语法有差异（如LIMIT、日期函数），需要告知LLM
    """

    dialect: str  # 数据库方言，如mysql
    version: str  # 数据库版本，如8.0.45


class DataAgentState(TypedDict):
    """
    Agent的核心状态，在整个图执行过程中不断被各节点更新
    每个字段对应agent流程中的一个阶段的输出

    数据流向：
    ┌─ query/chat_history ─→ clarify（检测是否需要补充）
    ├─ keywords ─→ extract_keywords（jieba分词）
    ├─ retrieved_columns/metrics/values ─→ recall_*（向量/全文召回）
    ├─ table_infos/metric_infos ─→ merge + filter（LLM裁剪）
    ├─ date_info/db_info ─→ add_extra_context（补充时间+DB信息）
    ├─ need_clarify ─→ clarify的条件边（True→END, False→继续）
    ├─ sql ─→ generate_sql / correct_sql（LLM生成/修正SQL）
    ├─ error ─→ validate_sql（EXPLAIN验证，None表示通过）
    └─ result ─→ execute_sql（SQL执行结果，供summarize读取）
    """

    query: str  # 用户输入的原始问题
    chat_history: list[dict]  # 对话历史 [{"role": "user/assistant", "content": "..."}]
    keywords: list[str]  # jieba抽取的关键词

    retrieved_columns: list[ColumnInfo]  # Qdrant召回的字段信息
    retrieved_metrics: list[MetricInfo]  # Qdrant召回的指标信息
    retrieved_values: list[ValueInfo]  # ES召回的字段取值

    table_infos: list[TableInfoState]  # 合并+过滤后的表信息
    metric_infos: list[MetricInfoState]  # 合并+过滤后的指标信息

    date_info: DateInfoState  # 日期上下文（数据最新日期，非系统时间）
    db_info: DBInfoState  # 数据库环境信息（方言+版本）

    need_clarify: bool  # 是否需要用户补充信息（clarify节点写入）
    sql: str  # LLM生成的SQL（generate_sql/correct_sql写入）

    error: str  # SQL验证时的错误信息，None表示验证通过（validate_sql写入）
    result: list[dict]  # SQL执行结果（execute_sql写入，summarize读取）

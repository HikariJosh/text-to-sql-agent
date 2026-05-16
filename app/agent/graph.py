"""
LangGraph状态图定义：定义agent的执行流程

图的拓扑结构：
  START → compact_history → clarify → (需要补充) END
                                → (信息完整) extract_keywords → [recall_column, recall_value, recall_metric](并行)
  → merge_retrieved_info → [filter_table, filter_metric](并行)
  → add_extra_context → think → generate_sql → validate_sql
  → (成功) execute_sql → summarize → END
  → (失败) correct_sql → execute_sql → summarize → END

节点说明：
  - compact_history: 对话历史压缩，超过阈值时用LLM将旧对话压缩为摘要
  - clarify: 信息完整性检测，过于模糊的查询会暂停流程向用户提问
  - extract_keywords: jieba分词抽取关键词，用于后续向量/全文召回
  - recall_column: Qdrant向量召回字段信息（语义相似度匹配）
  - recall_value: ES全文召回字段取值（关键词匹配，用于理解枚举值）
  - recall_metric: Qdrant向量召回指标信息（语义相似度匹配）
  - merge_retrieved_info: 合并3路召回结果，去重整理
  - filter_table: LLM裁剪不相关的表和字段，减少噪声
  - filter_metric: LLM裁剪不相关的指标，减少噪声
  - add_extra_context: 补充日期信息（取数据最新时间）和数据库环境信息
  - think: LLM分析用户意图，流式输出思考过程给前端（逐token推送）
  - generate_sql: LLM生成SQL语句
  - validate_sql: 通过EXPLAIN验证SQL语法正确性
  - correct_sql: SQL有语法错误时，LLM尝试修正
  - execute_sql: 在数据仓库上执行SQL，返回查询结果
  - summarize: LLM用自然语言总结查询结果

条件边说明：
  - clarify后: need_clarify=True→END（暂停等用户补充），False→extract_keywords
  - validate_sql后: error=None→execute_sql（语法正确），error不为None→correct_sql（先修正）

并行执行：
  - recall_column/recall_value/recall_metric 三者并行执行
  - filter_table/filter_metric 两者并行执行
"""

import asyncio

from langgraph.constants import END, START
from langgraph.graph import StateGraph

from app.agent.context import DataAgentContext
from app.agent.nodes.add_extra_context import add_extra_context
from app.agent.nodes.clarify import clarify
from app.agent.nodes.compact_history import compact_history
from app.agent.nodes.correct_sql import correct_sql
from app.agent.nodes.execute_sql import execute_sql
from app.agent.nodes.extract_keywords import extract_keywords
from app.agent.nodes.summarize import summarize
from app.agent.nodes.filter_metric import filter_metric
from app.agent.nodes.filter_table import filter_table
from app.agent.nodes.generate_sql import generate_sql
from app.agent.nodes.merge_retrieved_info import merge_retrieved_info
from app.agent.nodes.think import think
from app.agent.nodes.recall_column import recall_column
from app.agent.nodes.recall_metric import recall_metric
from app.agent.nodes.recall_value import recall_value
from app.agent.nodes.validate_sql import validate_sql
from app.agent.state import DataAgentState
from app.clients.embedding_client_manager import embedding_client_manager
from app.clients.es_client_manager import es_client_manager
from app.clients.mysql_client_manager import dw_mysql_client_manager, meta_mysql_client_manager
from app.clients.qdrant_client_manager import qdrant_client_manager
from app.repositories.embedding_repository import EmbeddingRepository
from app.repositories.es.value_repository import ValueRepository
from app.repositories.mysql.dw_repository import DWRepository
from app.repositories.mysql.meta_repository import MetaRepository
from app.repositories.qdrant.column_repository import ColumnRepository
from app.repositories.qdrant.metric_repository import MetricRepository

graph_builder = StateGraph(state_schema=DataAgentState, context_schema=DataAgentContext)

# ---- 添加节点 ----
graph_builder.add_node("compact_history", compact_history)  # 压缩对话历史
graph_builder.add_node("clarify", clarify)  # 检测信息缺失
graph_builder.add_node("extract_keywords", extract_keywords)  # jieba分词抽取关键词
graph_builder.add_node("recall_column", recall_column)  # Qdrant向量召回字段
graph_builder.add_node("recall_value", recall_value)  # ES全文召回取值
graph_builder.add_node("recall_metric", recall_metric)  # Qdrant向量召回指标
graph_builder.add_node("merge_retrieved_info", merge_retrieved_info)  # 合并3路召回结果
graph_builder.add_node("filter_metric", filter_metric)  # LLM裁剪不相关的指标
graph_builder.add_node("filter_table", filter_table)  # LLM裁剪不相关的表和列
graph_builder.add_node("add_extra_context", add_extra_context)  # 补充日期和DB版本信息
graph_builder.add_node("think", think)  # 思考分析（流式输出）
graph_builder.add_node("generate_sql", generate_sql)  # LLM生成SQL
graph_builder.add_node("validate_sql", validate_sql)  # EXPLAIN验证SQL语法
graph_builder.add_node("correct_sql", correct_sql)  # LLM修正错误的SQL
graph_builder.add_node("execute_sql", execute_sql)  # 执行SQL返回结果
graph_builder.add_node("summarize", summarize)  # 自然语言总结结果

# ---- 添加边：定义节点之间的执行顺序 ----
graph_builder.add_edge(START, "compact_history")
graph_builder.add_edge("compact_history", "clarify")

# clarify之后根据是否需要补充信息决定下一步
# need_clarify=True → 流程暂停（END），前端显示提问，用户补充后重新发起请求
# need_clarify=False → 继续执行extract_keywords
graph_builder.add_conditional_edges(
    "clarify",
    lambda state: "clarify_done" if state.get("need_clarify") else "extract_keywords",
    {"clarify_done": END, "extract_keywords": "extract_keywords"},
)

# extract_keywords之后3个召回节点并行执行（LangGraph自动调度）
graph_builder.add_edge("extract_keywords", "recall_column")
graph_builder.add_edge("extract_keywords", "recall_value")
graph_builder.add_edge("extract_keywords", "recall_metric")

# 3个召回节点汇聚到merge_retrieved_info（LangGraph自动等待全部完成）
graph_builder.add_edge("recall_column", "merge_retrieved_info")
graph_builder.add_edge("recall_value", "merge_retrieved_info")
graph_builder.add_edge("recall_metric", "merge_retrieved_info")

# merge之后2个过滤节点并行执行
graph_builder.add_edge("merge_retrieved_info", "filter_table")
graph_builder.add_edge("merge_retrieved_info", "filter_metric")

# 2个过滤节点汇聚到add_extra_context
graph_builder.add_edge("filter_table", "add_extra_context")
graph_builder.add_edge("filter_metric", "add_extra_context")

# 从add_extra_context开始是线性流程
graph_builder.add_edge("add_extra_context", "think")
graph_builder.add_edge("think", "generate_sql")
graph_builder.add_edge("generate_sql", "validate_sql")

# 条件边：根据validate_sql的结果决定下一步
# - error为None → 说明SQL语法正确，直接执行
# - error不为None → 说明SQL有语法错误，先修正再执行
graph_builder.add_conditional_edges(
    "validate_sql",
    lambda state: "execute_sql" if state["error"] is None else "correct_sql",
    {"execute_sql": "execute_sql", "correct_sql": "correct_sql"},
)

graph_builder.add_edge("correct_sql", "execute_sql")  # 修正后执行
graph_builder.add_edge("execute_sql", "summarize")  # 执行后生成自然语言总结
graph_builder.add_edge("summarize", END)  # 总结完毕结束

# 编译图，生成可执行的agent
graph = graph_builder.compile()


if __name__ == "__main__":

    async def test():
        embedding_client_manager.init()
        qdrant_client_manager.init()
        es_client_manager.init()
        meta_mysql_client_manager.init()
        dw_mysql_client_manager.init()

        async with (
            meta_mysql_client_manager.session_factory() as meta_session,
            dw_mysql_client_manager.session_factory() as dw_session,
        ):
            meta_mysql_repository = MetaRepository(meta_session)
            dw_mysql_repository = DWRepository(dw_session)
            column_qdrant_repository = ColumnRepository(qdrant_client_manager.client)
            value_es_repository = ValueRepository(es_client_manager.client)
            metric_qdrant_repository = MetricRepository(qdrant_client_manager.client)

            context = DataAgentContext(
                embedding_repository=EmbeddingRepository(embedding_client_manager),
                column_qdrant_repository=column_qdrant_repository,
                value_es_repository=value_es_repository,
                metric_qdrant_repository=metric_qdrant_repository,
                meta_mysql_repository=meta_mysql_repository,
                dw_mysql_repository=dw_mysql_repository,
            )
            state = DataAgentState(query="统计华北地区的销售总额")
        async for chunk in graph.astream(input=state, context=context, stream_mode="custom"):
            print(chunk)

        await qdrant_client_manager.close()
        await es_client_manager.close()
        await meta_mysql_client_manager.close()
        await dw_mysql_client_manager.close()

    asyncio.run(test())

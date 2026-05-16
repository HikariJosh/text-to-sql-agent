"""
Think节点：思考分析（流式输出）

职责：
  在生成SQL之前，先用LLM分析用户的查询意图，并将分析过程实时流式展示给用户。
  让用户看到系统理解了什么、选了哪些表和字段、时间范围如何处理，增加透明度。

在图中的位置：
  add_extra_context → think → generate_sql

流式输出实现：
  使用LangChain的astream_events API（version="v2"），监听on_chat_model_stream事件。
  每当LLM产出一个token，就通过runtime.stream_writer立即推送给前端，
  前端收到后逐字追加显示，实现打字机效果。

SSE事件：
  - {"type": "thinking", "content": "用户", "stream": true}  — 流式token，前端追加显示
  - {"type": "progress", "step": "思考分析", "status": "running/success/error"} — 进度状态

输入：
  - query: 用户原始问题
  - table_infos: 过滤后的表信息（含字段列表）
  - metric_infos: 过滤后的指标信息
  - date_info: 日期上下文（数据最新日期）

astream_events工作原理：
  chain.astream_events(input, version="v2") 会返回一个异步事件流，
  每个event是一个dict，包含：
  - event: 事件类型，如"on_chat_model_stream"（LLM输出token）、"on_chain_start"等
  - data: 事件数据，on_chat_model_stream时data["chunk"]是一个AIMessageChunk
  - name: 触发事件的组件名称

  我们只关心on_chat_model_stream事件中的token（chunk.content），
  将每个token通过writer推送给前端，前端收到后追加到思考文本中。
"""

import yaml
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.llm import llm
from app.agent.state import DataAgentState, DateInfoState, MetricInfoState, TableInfoState
from app.core.log import logger
from app.prompt.prompt_loader import load_prompt


async def think(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """
    思考节点：在生成SQL前分析用户意图，自检计算逻辑，流式输出给用户

    职责：
      1. 分析用户想算什么
      2. 想清楚计算逻辑（分子分母、是否需要LEAD追踪路径、JOIN关系等）
      3. 自检：检查自己的分析是否有逻辑漏洞
      4. 规划SQL结构

    这样在think阶段就确保逻辑正确，validate_sql只需要做EXPLAIN语法检查。
    """
    writer = runtime.stream_writer
    writer({"type": "progress", "step": "思考分析", "status": "running"})

    query: str = state["query"]
    table_infos: list[TableInfoState] = state["table_infos"]
    metric_infos: list[MetricInfoState] = state["metric_infos"]
    date_info: DateInfoState = state["date_info"]

    try:
        prompt = PromptTemplate(
            template=load_prompt("think"),
            input_variables=["query", "table_infos", "metric_infos", "date_info"],
        )
        chain = prompt | llm | StrOutputParser()

        full_text = ""
        async for event in chain.astream_events(
            {
                "query": query,
                "table_infos": yaml.dump(table_infos, allow_unicode=True, sort_keys=False),
                "metric_infos": yaml.dump(metric_infos, allow_unicode=True, sort_keys=False),
                "date_info": yaml.dump(date_info, allow_unicode=True, sort_keys=False),
            },
            version="v2",
        ):
            kind = event["event"]
            if kind == "on_chat_model_stream":
                chunk = event["data"].get("chunk")
                if chunk and hasattr(chunk, "content") and chunk.content:
                    full_text += chunk.content
                    writer({"type": "thinking", "content": chunk.content, "stream": True})

        writer({"type": "progress", "step": "思考分析", "status": "success"})
        logger.info(f"思考分析: {full_text.strip()}")

    except Exception as e:
        writer({"type": "progress", "step": "思考分析", "status": "error"})
        logger.error(f"思考分析失败: {e}")

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
    思考节点：在生成SQL前分析用户意图，流式输出给用户

    支持重入：当validate_sql检测到逻辑错误时，会带错误反馈重新进入此节点，
    LLM会基于上次的错误信息重新分析计算逻辑，生成更准确的SQL。
    """
    writer = runtime.stream_writer
    writer({"type": "progress", "step": "思考分析", "status": "running"})

    # 从state中读取上游节点产出的数据
    query: str = state["query"]
    table_infos: list[TableInfoState] = state["table_infos"]
    metric_infos: list[MetricInfoState] = state["metric_infos"]
    date_info: DateInfoState = state["date_info"]
    error: str = state.get("error")
    error_type: str = state.get("error_type", "")
    sql: str = state.get("sql", "")

    # 构建错误反馈上下文（仅逻辑错误重入时有值）
    error_context = ""
    if error and error_type == "logic":
        error_context = f"""
【上次生成的SQL（存在逻辑问题）】
{sql}

【逻辑问题描述】
{error}

请仔细分析上述逻辑问题，重新思考正确的计算方式，然后给出修正后的分析。
"""

    try:
        # 构建LangChain链：prompt → llm → output_parser
        prompt = PromptTemplate(
            template=load_prompt("think"),
            input_variables=["query", "table_infos", "metric_infos", "date_info", "error_context"],
        )
        chain = prompt | llm | StrOutputParser()

        # 使用astream_events获取LLM的逐token输出
        # version="v2" 是LangChain 0.2+推荐的事件流版本
        full_text = ""
        async for event in chain.astream_events(
            {
                "query": query,
                # table_infos/metric_infos是复杂对象，需要YAML序列化后传给prompt
                "table_infos": yaml.dump(table_infos, allow_unicode=True, sort_keys=False),
                "metric_infos": yaml.dump(metric_infos, allow_unicode=True, sort_keys=False),
                "date_info": yaml.dump(date_info, allow_unicode=True, sort_keys=False),
                "error_context": error_context,
            },
            version="v2",
        ):
            kind = event["event"]
            # on_chat_model_stream: LLM每次产出一个token时触发
            # event["data"]["chunk"] 是一个AIMessageChunk对象，.content是文本内容
            if kind == "on_chat_model_stream":
                chunk = event["data"].get("chunk")
                if chunk and hasattr(chunk, "content") and chunk.content:
                    full_text += chunk.content
                    # stream=True 标记这是流式token，前端需要追加而非替换
                    writer({"type": "thinking", "content": chunk.content, "stream": True})

        writer({"type": "progress", "step": "思考分析", "status": "success"})
        logger.info(f"思考分析: {full_text.strip()}")

    except Exception as e:
        writer({"type": "progress", "step": "思考分析", "status": "error"})
        logger.error(f"思考分析失败: {e}")

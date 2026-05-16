"""
Summarize节点：自然语言总结查询结果

职责：
  在SQL执行完毕后，将查询结果用自然语言陈述给用户。
  比如"2012年3月，gsearch来源的会话数最多，共1860次，占总会话的99%"。
  让用户不需要自己看表格就能理解关键发现。

在图中的位置：
  execute_sql → summarize → END

输入：
  - query: 用户原始问题，让LLM理解用户关注什么
  - sql: 生成的SQL，让LLM理解数据的口径和过滤条件
  - result: SQL执行结果（list[dict]），由execute_sql节点写入state

SSE事件：
  - {"type": "summary", "content": "gsearch占比最多..."} — 自然语言总结文本

容错：
  - 总结失败不影响已有的表格结果展示，只打日志不抛异常
"""

import json

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.llm import llm
from app.agent.state import DataAgentState
from app.core.log import logger
from app.prompt.prompt_loader import load_prompt


async def summarize(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """总结节点：用自然语言陈述查询结果"""
    writer = runtime.stream_writer
    writer({"type": "progress", "step": "生成总结", "status": "running"})

    # 从state中读取用户问题、生成的SQL、执行结果
    query: str = state["query"]
    sql: str = state["sql"]
    result: list[dict] = state.get("result", [])

    try:
        # 加载summarize.prompt模板，传入query/sql/result三个变量
        # result需要序列化为JSON字符串，default=str处理datetime等非标准类型
        prompt = PromptTemplate(
            template=load_prompt("summarize"),
            input_variables=["query", "sql", "result"],
        )
        chain = prompt | llm | StrOutputParser()

        result_text = await chain.ainvoke(
            {
                "query": query,
                "sql": sql,
                "result": json.dumps(result, ensure_ascii=False, default=str),
            }
        )

        writer({"type": "progress", "step": "生成总结", "status": "success"})
        # summary事件：前端收到后展示为普通文本气泡
        writer({"type": "summary", "content": result_text.strip()})
        logger.info(f"查询总结: {result_text.strip()}")

    except Exception as e:
        # 总结失败不抛异常，表格结果已经通过result事件发给前端了
        writer({"type": "progress", "step": "生成总结", "status": "error"})
        logger.error(f"生成总结失败: {e}")

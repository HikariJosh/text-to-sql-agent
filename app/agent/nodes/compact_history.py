from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.llm import llm
from app.agent.state import DataAgentState
from app.core.log import logger

MAX_HISTORY_TURNS = 5
KEEP_RECENT_TURNS = 2

COMPRESS_PROMPT = """请将以下多轮对话压缩为一段简洁的摘要，保留关键信息（用户关注的业务主题、已查询的指标、已确认的维度等），供后续SQL生成参考。

对话历史：
{history}

要求：
- 用一段话概括，不超过200字
- 保留具体的业务术语和数据维度
- 不要遗漏用户的核心关注点

摘要："""


async def compact_history(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """压缩对话历史：超过阈值时用LLM将旧对话压缩为摘要"""
    chat_history: list[dict] = state.get("chat_history", [])

    if len(chat_history) <= MAX_HISTORY_TURNS:
        return {}

    # 拆分：旧对话（需要压缩） + 最近对话（保留原文）
    old_turns = chat_history[:-KEEP_RECENT_TURNS]
    recent_turns = chat_history[-KEEP_RECENT_TURNS:]

    # 格式化旧对话
    history_lines = []
    for turn in old_turns:
        role = "用户" if turn["role"] == "user" else "助手"
        history_lines.append(f"{role}: {turn['content']}")
    history_text = "\n".join(history_lines)

    try:
        prompt = PromptTemplate(template=COMPRESS_PROMPT, input_variables=["history"])
        chain = prompt | llm | StrOutputParser()
        summary = await chain.ainvoke({"history": history_text})

        compressed = [{"role": "system", "content": f"[历史摘要] {summary.strip()}"}] + recent_turns
        logger.info(f"对话历史已压缩: {len(chat_history)}轮 -> 1条摘要 + {len(recent_turns)}轮")
        return {"chat_history": compressed}
    except Exception as e:
        logger.error(f"压缩对话历史失败: {e}, 保留最近{KEEP_RECENT_TURNS}轮")
        return {"chat_history": recent_turns}

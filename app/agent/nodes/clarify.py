"""
Clarify节点：信息完整性检测

职责：
  在agent流程最前面检测用户的查询是否足够清晰，能否据此生成SQL。
  如果查询过于模糊（如"看看数据"），则暂停流程，通过SSE向用户提问，
  用户补充信息后重新进入流程。

触发条件：
  - 仅在首轮对话时触发（无chat_history）
  - 有历史对话时直接跳过，让下游的generate_sql结合上下文自行理解

判断策略（通过LLM实现）：
  - 宽松策略：只要用户表达了明确的分析意图就放行
  - 时间范围不强制要求：系统会默认使用数据最新月份（见add_extra_context节点）
  - 只有完全无法判断意图的极端模糊查询才触发提问

SSE事件：
  - {"type": "clarify", "message": "请告诉我想查什么数据？"} — 需要用户补充时发送

状态读写：
  - 读取：query（用户原始问题）、chat_history（对话历史）
  - 写入：need_clarify（True=需要补充 / False=信息完整）
"""

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.llm import llm
from app.agent.state import DataAgentState
from app.core.log import logger
from app.prompt.prompt_loader import load_prompt


async def clarify(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """检测查询是否缺少关键信息，如果缺失则向用户提问"""
    writer = runtime.stream_writer

    query: str = state["query"]
    chat_history: list[dict] = state.get("chat_history", [])

    # 有历史对话时跳过clarify，让generate_sql结合历史自行理解
    # 原因：用户回复clarify提问时（如"2012年3月"），会带上之前的chat_history，
    # 此时不应再次触发clarify，否则会导致无限提问循环
    if chat_history:
        return {"need_clarify": False}

    # 格式化历史（最近3轮），作为上下文传给LLM辅助判断
    # 注意：上面已经return了，这里实际上只有chat_history为空时才会执行
    if chat_history:
        history_lines = []
        for turn in chat_history[-3:]:
            role = "用户" if turn["role"] == "user" else "助手"
            history_lines.append(f"{role}: {turn['content']}")
        history_text = "\n".join(history_lines)
    else:
        history_text = "无"

    try:
        # 调用LLM判断信息是否完整
        prompt = PromptTemplate(template=load_prompt("clarify"), input_variables=["query", "chat_history"])
        chain = prompt | llm | StrOutputParser()
        result = await chain.ainvoke({"query": query, "chat_history": history_text})
        result = result.strip()

        # LLM回复"OK"表示信息完整，流程继续
        if result.upper() == "OK":
            logger.info("查询信息完整，无需补充")
            return {"need_clarify": False}

        # LLM返回了提问内容，通过SSE发给前端，流程暂停（图走到END）
        writer({"type": "clarify", "message": result})
        logger.info(f"需要用户补充信息: {result}")
        return {"need_clarify": True}

    except Exception as e:
        # 异常时放行，不因为clarify失败阻断整个流程
        logger.error(f"clarify节点异常: {e}, 跳过")
        return {"need_clarify": False}

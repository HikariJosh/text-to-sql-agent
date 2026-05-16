import yaml
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.llm import llm
from app.agent.state import DataAgentState, DateInfoState, MetricInfoState, TableInfoState
from app.core.log import logger
from app.prompt.prompt_loader import load_prompt


async def generate_sql(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """
    生成SQL：将用户的自然语言问题和所有上下文信息发给LLM，让LLM生成SQL
    上下文包括：表结构信息、指标信息、日期信息、数据库版本信息
    所有信息序列化为YAML格式传给LLM，因为YAML对LLM来说可读性最好
    """
    writer = runtime.stream_writer
    writer({"type": "progress", "step": "生成SQL", "status": "running"})

    query: str = state["query"]
    chat_history: list[dict] = state.get("chat_history", [])
    table_infos: list[TableInfoState] = state["table_infos"]
    metric_infos: list[MetricInfoState] = state["metric_infos"]
    date_info: DateInfoState = state["date_info"]
    db_info: dict[str, str] = state["db_info"]

    # 将对话历史格式化为可读字符串
    if chat_history:
        history_lines = []
        for turn in chat_history:
            role = "用户" if turn["role"] == "user" else "助手"
            history_lines.append(f"{role}: {turn['content']}")
        chat_history_text = "\n".join(history_lines)
    else:
        chat_history_text = "无"

    try:
        prompt = PromptTemplate(
            template=load_prompt("generate_sql"),
            input_variables=["query", "chat_history", "table_infos", "metric_infos", "date_info", "db_info"],
        )
        # 直接将LLM输出的SQL作为字符串返回，不进行JSON等额外解析
        output_parser = StrOutputParser()

        chain = prompt | llm | output_parser

        result = await chain.ainvoke(
            {
                "query": query,
                "chat_history": chat_history_text,
                "table_infos": yaml.dump(table_infos, allow_unicode=True, sort_keys=False),
                "metric_infos": yaml.dump(metric_infos, allow_unicode=True, sort_keys=False),
                "date_info": yaml.dump(date_info, allow_unicode=True, sort_keys=False),
                "db_info": yaml.dump(db_info, allow_unicode=True, sort_keys=False),
            }
        )

        writer({"type": "progress", "step": "生成SQL", "status": "success"})
        # SQL暂存到state，不直接展示给用户，等validate通过后再展示
        writer({"type": "thinking", "content": f"生成SQL：\n```sql\n{result}\n```", "stream": False})
        logger.info(f"生成的SQL: {result}")
        return {"sql": result}
    except Exception as e:
        writer({"type": "progress", "step": "生成SQL", "status": "error"})
        logger.error(f"生成SQL失败: {str(e)}")
        raise

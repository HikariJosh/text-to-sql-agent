import yaml
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.llm import llm
from app.agent.state import DataAgentState, TableInfoState
from app.core.log import logger
from app.prompt.prompt_loader import load_prompt
from app.repositories.mysql.dw_repository import DWRepository


async def validate_sql(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """
    验证SQL：两步验证
    1. EXPLAIN 检查语法（数据库层面）
    2. LLM 检查逻辑（业务层面）：窗口函数排序、漏斗计算、比率除零等

    验证结果会写入state["error"]，图的条件边根据这个值决定下一步：
    - error=None → 直接执行SQL
    - error≠None → 先让LLM修正SQL
    """
    writer = runtime.stream_writer
    writer({"type": "progress", "step": "验证SQL", "status": "running"})

    dw_mysql_repository: DWRepository = runtime.context["dw_mysql_repository"]
    query: str = state["query"]
    sql: str = state["sql"]
    table_infos: list[TableInfoState] = state["table_infos"]

    # 第1步：EXPLAIN 语法检查
    try:
        await dw_mysql_repository.validate_sql(sql)
        logger.info(f"SQL语法验证通过: {sql}")
    except Exception as e:
        writer({"type": "progress", "step": "验证SQL", "status": "error"})
        logger.error(f"SQL语法验证失败: {str(e)}")
        return {"error": str(e)}

    # 第2步：LLM 逻辑检查
    try:
        prompt = PromptTemplate(
            template=load_prompt("validate_sql"),
            input_variables=["query", "sql", "table_infos"],
        )
        chain = prompt | llm | StrOutputParser()
        result = await chain.ainvoke({
            "query": query,
            "sql": sql,
            "table_infos": yaml.dump(table_infos, allow_unicode=True, sort_keys=False),
        })
        result = result.strip()

        if result.upper() == "OK":
            writer({"type": "progress", "step": "验证SQL", "status": "success"})
            logger.info("SQL逻辑验证通过")
            return {"error": None}
        else:
            # 逻辑有问题，把问题描述写入error，让correct_sql修正
            writer({"type": "progress", "step": "验证SQL", "status": "error"})
            logger.warning(f"SQL逻辑问题: {result}")
            return {"error": f"逻辑问题: {result}"}
    except Exception as e:
        # LLM检查失败不影响流程，继续执行
        writer({"type": "progress", "step": "验证SQL", "status": "success"})
        logger.warning(f"SQL逻辑检查跳过（LLM调用失败）: {str(e)}")
        return {"error": None}

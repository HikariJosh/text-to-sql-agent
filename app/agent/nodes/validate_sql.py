from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.state import DataAgentState
from app.core.log import logger
from app.repositories.mysql.dw_repository import DWRepository


async def validate_sql(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """
    验证SQL：通过EXPLAIN检查SQL语法是否正确
    不会真正执行SQL，只检查语法和表/字段是否存在
    验证结果会写入state["error"]，图的条件边根据这个值决定下一步：
    - error=None → 直接执行SQL
    - error≠None → 先让LLM修正SQL
    """
    writer = runtime.stream_writer
    writer({"type": "progress", "step": "验证SQL", "status": "running"})

    dw_mysql_repository: DWRepository = runtime.context["dw_mysql_repository"]

    sql = state["sql"]

    try:
        await dw_mysql_repository.validate_sql(sql)
        writer({"type": "progress", "step": "验证SQL", "status": "success"})
        logger.info(f"SQL验证成功: {sql}")
        return {"error": None}
    except Exception as e:
        # 验证失败不抛异常，而是把错误信息写入state，让条件边决定走correct_sql
        writer({"type": "progress", "step": "验证SQL", "status": "error"})
        logger.error(f"SQL验证失败: {str(e)}")
        return {"error": str(e)}

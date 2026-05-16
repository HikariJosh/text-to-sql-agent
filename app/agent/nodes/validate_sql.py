"""
Validate SQL节点：EXPLAIN语法检查

职责：
  通过EXPLAIN检查SQL语法是否正确，不会真正执行SQL。
  只检查语法和表/字段是否存在，不检查逻辑正确性（逻辑在think阶段自检）。

验证结果会写入state["error"]，图的条件边根据这个值决定下一步：
  - error=None → 直接执行SQL
  - error≠None → 先让LLM修正SQL（correct_sql节点）

在图中的位置：
  generate_sql → validate_sql → (成功) execute_sql
                              → (失败) correct_sql → execute_sql
"""

from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.state import DataAgentState
from app.core.log import logger
from app.repositories.mysql.dw_repository import DWRepository


async def validate_sql(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """
    EXPLAIN语法检查：验证SQL能否被数据库解析
    验证通过后才将SQL展示给用户（发送sql事件）
    """
    writer = runtime.stream_writer
    writer({"type": "progress", "step": "验证SQL", "status": "running"})

    dw_mysql_repository: DWRepository = runtime.context["dw_mysql_repository"]
    sql: str = state["sql"]

    try:
        await dw_mysql_repository.validate_sql(sql)
        writer({"type": "progress", "step": "验证SQL", "status": "success"})
        writer({"type": "thinking", "content": "SQL语法验证通过", "stream": False})
        # 验证通过，此时才将SQL正式展示给用户
        writer({"type": "sql", "sql": sql})
        logger.info(f"SQL验证成功: {sql}")
        return {"error": None}
    except Exception as e:
        writer({"type": "progress", "step": "验证SQL", "status": "error"})
        writer({"type": "thinking", "content": f"SQL语法验证失败：{e}", "stream": False})
        logger.error(f"SQL验证失败: {str(e)}")
        return {"error": str(e)}

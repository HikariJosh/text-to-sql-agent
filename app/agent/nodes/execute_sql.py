"""
Execute SQL节点：执行SQL并返回结果

职责：
  在数据仓库（MySQL）上执行最终生成的SQL，将查询结果通过SSE发给前端展示表格，
  同时将结果写入state供下游的summarize节点读取。

在图中的位置：
  generate_sql → validate_sql → execute_sql → summarize → END
  或：generate_sql → validate_sql → correct_sql → execute_sql → summarize → END

SSE事件：
  - {"type": "progress", "step": "执行SQL", "status": "running/success/error"}
  - {"type": "result", "data": [...]} — 查询结果，前端收到后渲染为表格

状态写入：
  - result: list[dict] — SQL执行结果，每行是一个dict，key是列名，value是列值
    例：[{"utm_source": "gsearch", "session_count": 1860}, ...]
    值已经是JSON安全的（datetime→ISO字符串，Decimal→float，由DWRepository处理）

注意：
  - execute_sql是图中唯一真正访问数据仓库的节点
  - 执行失败会抛异常，被外层的query_service捕获后返回error事件给前端
"""

from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.state import DataAgentState
from app.core.log import logger


async def execute_sql(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """
    执行SQL：在数据仓库上执行最终的SQL，返回查询结果
    通过stream_writer发送两种事件：
    - progress: 告诉前端执行状态
    - result: 返回实际的查询结果数据
    结果同时写入state的result字段，供下游summarize节点读取
    """
    writer = runtime.stream_writer
    writer({"type": "progress", "step": "执行SQL", "status": "running"})

    sql = state["sql"]

    dw_mysql_repository = runtime.context["dw_mysql_repository"]

    try:
        result = await dw_mysql_repository.execute_sql(sql)

        writer({"type": "progress", "step": "执行SQL", "status": "success"})
        # result事件：前端收到后提取列名(Object.keys)渲染表头，遍历行渲染数据
        writer({"type": "result", "data": result})
        logger.info(f"执行SQL结果: {result}")
        # 将结果写入state，供下游summarize节点读取生成自然语言总结
        # LangGraph中节点通过return dict来更新state
        return {"result": result}

    except Exception as e:
        writer({"type": "progress", "step": "执行SQL", "status": "error"})
        logger.error(f"执行SQL失败:{str(e)}")
        raise

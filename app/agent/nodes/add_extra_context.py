"""
Add Extra Context节点：补充日期和数据库环境信息

职责：
  为下游的think和generate_sql节点提供时间参考和数据库环境信息。

日期信息（date_info）：
  关键设计：日期取自数据表的最新时间，而非系统当前时间。
  原因：项目中的数据集可能是历史数据（如2012-2015年），如果用当前系统时间（2026年），
  用户问"本月"时会生成 WHERE created_at >= '2026-05-01'，但数据中根本没有2026年的记录。

  实现：执行 SELECT MAX(created_at) FROM website_sessions 获取数据的最新日期，
  用这个日期作为"今天"，让LLM理解相对时间表达（本月、最近7天等）。

  示例：如果数据最新日期是 2015-03-19，则：
  - "本月" → 2015年3月（2015-03-01 ~ 2015-04-01）
  - "最近7天" → 2015-03-12 ~ 2015-03-19

  降级策略：如果查询MAX(created_at)失败（表不存在或为空），回退到系统当前时间。

数据库环境信息（db_info）：
  查询数据库版本和方言（如 mysql 8.0.45），帮助LLM生成语法正确的SQL。
  不同数据库的SQL语法有差异，如LIMIT、日期函数、字符串函数等。

SSE事件：
  - {"type": "progress", "step": "添加额外上下文信息", "status": "running/success/error"}

状态写入：
  - date_info: DateInfoState(date="2015-03-19", weekday="Thursday", quarter="Q1")
  - db_info: DBInfoState(dialect="mysql", version="8.0.45")
"""

from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.state import DataAgentState, DateInfoState
from app.core.log import logger


async def add_extra_context(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """
    添加额外上下文信息：补充日期信息和数据库环境信息
    日期取自数据表的最新时间（而非当前时间），确保对历史数据集也能正确处理相对时间
    """
    writer = runtime.stream_writer
    writer({"type": "progress", "step": "添加额外上下文信息", "status": "running"})

    dw_mysql_repository = runtime.context["dw_mysql_repository"]

    try:
        # 从数据表获取最新日期，而非使用当前时间
        # 原因：数据集可能是历史数据（如2012-2015年），用当前时间会导致相对时间计算错误
        latest = await dw_mysql_repository.execute_sql(
            "SELECT MAX(created_at) AS latest FROM website_sessions"
        )
        if latest and latest[0].get("latest"):
            from datetime import datetime

            raw = latest[0]["latest"]
            # execute_sql返回的datetime可能是str或datetime对象，需要兼容处理
            if isinstance(raw, str):
                dt = datetime.fromisoformat(raw)
            else:
                dt = raw
            date = dt.strftime("%Y-%m-%d")
            weekday = dt.strftime("%A")
            quarter = f"Q{(dt.month - 1) // 3 + 1}"
        else:
            # 降级：查询失败时使用系统当前时间
            from datetime import datetime

            today = datetime.today()
            date = today.strftime("%Y-%m-%d")
            weekday = today.strftime("%A")
            quarter = f"Q{(today.month - 1) // 3 + 1}"

        date_info = DateInfoState(date=date, weekday=weekday, quarter=quarter)

        # 获取数据仓库环境信息(版本、方言)，用于generate_sql生成语法正确的SQL
        db_info = await dw_mysql_repository.get_db_info()

        writer({"type": "progress", "step": "添加额外上下文信息", "status": "success"})
        logger.info(f"额外上下文信息：数据库信息-{db_info} 日期信息-{date_info}")

        return {
            "date_info": date_info,
            "db_info": db_info,
        }
    except Exception as e:
        writer({"type": "progress", "step": "添加额外上下文信息", "status": "error"})
        logger.error(f"添加上下文失败:{str(e)}")
        raise

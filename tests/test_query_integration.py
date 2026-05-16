"""
集成测试：测试 agent 对不同类型查询的处理

需要先启动基础设施：make up
运行方式：pytest tests/test_query_integration.py -v -s
"""

import asyncio
import json

import pytest

from app.agent.context import DataAgentContext
from app.agent.graph import graph
from app.agent.state import DataAgentState
from app.clients.embedding_client_manager import embedding_client_manager
from app.clients.es_client_manager import es_client_manager
from app.clients.mysql_client_manager import dw_mysql_client_manager, meta_mysql_client_manager
from app.clients.qdrant_client_manager import qdrant_client_manager
from app.repositories.embedding_repository import EmbeddingRepository
from app.repositories.es.value_repository import ValueRepository
from app.repositories.mysql.dw_repository import DWRepository
from app.repositories.mysql.meta_repository import MetaRepository
from app.repositories.qdrant.column_repository import ColumnRepository
from app.repositories.qdrant.metric_repository import MetricRepository


@pytest.fixture(scope="module")
def setup():
    """初始化所有外部服务连接"""
    embedding_client_manager.init()
    qdrant_client_manager.init()
    es_client_manager.init()
    meta_mysql_client_manager.init()
    dw_mysql_client_manager.init()
    yield
    asyncio.get_event_loop().run_until_complete(qdrant_client_manager.close())
    asyncio.get_event_loop().run_until_complete(es_client_manager.close())


@pytest.fixture(scope="module")
def context(setup):
    """创建 agent context"""

    async def _create():
        meta_session_cm = meta_mysql_client_manager.session_factory()
        dw_session_cm = dw_mysql_client_manager.session_factory()
        meta_session = await meta_session_cm.__aenter__()
        dw_session = await dw_session_cm.__aenter__()

        ctx = DataAgentContext(
            embedding_repository=EmbeddingRepository(embedding_client_manager),
            column_qdrant_repository=ColumnRepository(qdrant_client_manager.client),
            value_es_repository=ValueRepository(es_client_manager.client),
            metric_qdrant_repository=MetricRepository(qdrant_client_manager.client),
            meta_mysql_repository=MetaRepository(meta_session),
            dw_mysql_repository=DWRepository(dw_session),
        )
        return ctx, meta_session_cm, dw_session_cm

    ctx, meta_cm, dw_cm = asyncio.get_event_loop().run_until_complete(_create())
    yield ctx
    asyncio.get_event_loop().run_until_complete(meta_cm.__aexit__(None, None, None))
    asyncio.get_event_loop().run_until_complete(dw_cm.__aexit__(None, None, None))


async def run_query(context: DataAgentContext, query: str, chat_history: list[dict] = None):
    """执行查询并收集所有事件"""
    state = DataAgentState(query=query, chat_history=chat_history or [])
    events = []
    async for chunk in graph.astream(input=state, context=context, stream_mode="custom"):
        events.append(chunk)
    return events


def extract_sql(events):
    """从事件中提取生成的SQL"""
    for e in events:
        if e.get("type") == "sql":
            return e.get("sql", "")
    return None


def extract_result(events):
    """从事件中提取查询结果"""
    for e in events:
        if e.get("type") == "result":
            return e.get("data", [])
    return None


def extract_error(events):
    """从事件中提取错误信息"""
    for e in events:
        if e.get("type") == "error":
            return e.get("message", "")
    return None


def has_step_status(events, step, status):
    """检查某个步骤是否达到了指定状态"""
    for e in events:
        if e.get("type") == "progress" and e.get("step") == step and e.get("status") == status:
            return True
    return False


@pytest.mark.asyncio
async def test_simple_count(context):
    """简单统计：各渠道的会话数"""
    events = await run_query(context, "各渠道的会话数有多少")
    sql = extract_sql(events)
    result = extract_result(events)
    error = extract_error(events)

    assert error is None, f"查询出错: {error}"
    assert sql is not None, "未生成SQL"
    assert result is not None, "未返回结果"
    assert len(result) > 0, "结果为空"
    print(f"\nSQL: {sql}")
    print(f"结果: {result[:3]}")


@pytest.mark.asyncio
async def test_top_n_ranking(context):
    """排名查询：销量top10的产品"""
    events = await run_query(context, "销量最高的10个产品是哪些")
    sql = extract_sql(events)
    result = extract_result(events)
    error = extract_error(events)

    assert error is None, f"查询出错: {error}"
    assert sql is not None, "未生成SQL"
    assert result is not None, "未返回结果"
    assert len(result) <= 10, f"结果超过10条: {len(result)}"
    print(f"\nSQL: {sql}")
    print(f"结果数量: {len(result)}")


@pytest.mark.asyncio
async def test_time_filter(context):
    """时间范围查询：最近一个月的订单总金额"""
    events = await run_query(context, "最近一个月的订单总金额是多少")
    sql = extract_sql(events)
    result = extract_result(events)
    error = extract_error(events)

    assert error is None, f"查询出错: {error}"
    assert sql is not None, "未生成SQL"
    assert result is not None, "未返回结果"
    print(f"\nSQL: {sql}")
    print(f"结果: {result}")


@pytest.mark.asyncio
async def test_funnel_conversion(context):
    """漏斗转化率：从商品页到购物车的转化率"""
    events = await run_query(context, "从商品页到购物车的转化率是多少")
    sql = extract_sql(events)
    result = extract_result(events)
    error = extract_error(events)

    assert error is None, f"查询出错: {error}"
    assert sql is not None, "未生成SQL"
    assert result is not None, "未返回结果"
    # 检查SQL是否使用了LEAD（正确的漏斗分析方式）
    assert "LEAD" in sql.upper() or "lead" in sql, f"漏斗查询应使用LEAD，实际SQL: {sql}"
    print(f"\nSQL: {sql}")
    print(f"结果: {result}")


@pytest.mark.asyncio
async def test_multi_table_join(context):
    """多表关联：各产品的退款率"""
    events = await run_query(context, "各产品的退款率是多少")
    sql = extract_sql(events)
    result = extract_result(events)
    error = extract_error(events)

    assert error is None, f"查询出错: {error}"
    assert sql is not None, "未生成SQL"
    assert result is not None, "未返回结果"
    print(f"\nSQL: {sql}")
    print(f"结果: {result[:3]}")


@pytest.mark.asyncio
async def test_group_by_dimension(context):
    """分维度统计：不同设备类型的会话数"""
    events = await run_query(context, "不同设备类型的会话数分别是多少")
    sql = extract_sql(events)
    result = extract_result(events)
    error = extract_error(events)

    assert error is None, f"查询出错: {error}"
    assert sql is not None, "未生成SQL"
    assert result is not None, "未返回结果"
    assert len(result) >= 2, f"设备类型应该至少有2种，实际: {len(result)}"
    print(f"\nSQL: {sql}")
    print(f"结果: {result}")


@pytest.mark.asyncio
async def test_ratio_calculation(context):
    """比率计算：新客占比"""
    events = await run_query(context, "新客占比是多少")
    sql = extract_sql(events)
    result = extract_result(events)
    error = extract_error(events)

    assert error is None, f"查询出错: {error}"
    assert sql is not None, "未生成SQL"
    assert result is not None, "未返回结果"
    print(f"\nSQL: {sql}")
    print(f"结果: {result}")


@pytest.mark.asyncio
async def test_trend_analysis(context):
    """趋势分析：每月订单数的变化趋势"""
    events = await run_query(context, "每月订单数的变化趋势")
    sql = extract_sql(events)
    result = extract_result(events)
    error = extract_error(events)

    assert error is None, f"查询出错: {error}"
    assert sql is not None, "未生成SQL"
    assert result is not None, "未返回结果"
    assert len(result) > 1, "趋势查询应返回多个时间点"
    print(f"\nSQL: {sql}")
    print(f"结果数量: {len(result)}")


@pytest.mark.asyncio
async def test_clarify_vague_query(context):
    """模糊查询：应该触发clarify提问"""
    events = await run_query(context, "帮我看一下")
    # 检查是否有clarify事件或直接跳过（取决于LLM判断）
    has_clarify = any(e.get("type") == "clarify" for e in events)
    has_sql = any(e.get("type") == "sql" for e in events)
    # 模糊查询应该触发clarify或者直接生成SQL（取决于宽松程度）
    assert has_clarify or has_sql, "模糊查询应触发clarify或生成SQL"
    print(f"\n触发clarify: {has_clarify}, 生成SQL: {has_sql}")


@pytest.mark.asyncio
async def test_multi_turn_conversation(context):
    """多轮对话：第二轮应理解上下文"""
    # 第一轮：查询各渠道会话数
    events1 = await run_query(context, "各渠道的会话数有多少")
    result1 = extract_result(events1)
    assert result1 is not None, "第一轮查询失败"

    # 构造对话历史
    chat_history = [
        {"role": "user", "content": "各渠道的会话数有多少"},
        {"role": "assistant", "content": extract_sql(events1) or ""},
    ]

    # 第二轮：追问
    events2 = await run_query(context, "哪个渠道最多", chat_history=chat_history)
    sql2 = extract_sql(events2)
    result2 = extract_result(events2)
    error2 = extract_error(events2)

    assert error2 is None, f"第二轮查询出错: {error2}"
    assert sql2 is not None, "第二轮未生成SQL"
    assert result2 is not None, "第二轮未返回结果"
    print(f"\n第二轮SQL: {sql2}")
    print(f"结果: {result2}")

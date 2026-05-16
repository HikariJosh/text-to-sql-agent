import asyncio
import json

from app.agent.context import DataAgentContext
from app.agent.graph import graph
from app.agent.state import DataAgentState
from app.repositories.embedding_repository import EmbeddingRepository
from app.repositories.es.value_repository import ValueRepository
from app.repositories.mysql.dw_repository import DWRepository
from app.repositories.mysql.meta_repository import MetaRepository
from app.repositories.qdrant.column_repository import ColumnRepository
from app.repositories.qdrant.metric_repository import MetricRepository

# 查询执行超时时间（秒）
QUERY_TIMEOUT_SECONDS = 120


class QueryService:
    """
    查询服务：编排agent图的执行，把每个节点的输出转为SSE流式响应返回前端
    接收依赖注入的所有repo和client，组装成agent所需的context
    """

    def __init__(
        self,
        embedding_repository: EmbeddingRepository,
        column_qdrant_repository: ColumnRepository,
        value_es_repository: ValueRepository,
        metric_qdrant_repository: MetricRepository,
        meta_mysql_repository: MetaRepository,
        dw_mysql_repository: DWRepository,
    ):
        self.embedding_repository = embedding_repository
        self.column_qdrant_repository = column_qdrant_repository
        self.value_es_repository = value_es_repository
        self.metric_qdrant_repository = metric_qdrant_repository
        self.meta_mysql_repository = meta_mysql_repository
        self.dw_mysql_repository = dw_mysql_repository

    async def query(self, query: str, chat_history: list[dict] | None = None):
        """
        执行查询流程：创建context和state → 调用graph.astream流式执行 → 逐chunk转为SSE格式
        SSE格式: data: {"type": "progress/result", ...}\n\n
        """
        # 组装agent上下文，包含所有外部服务的repo和client
        context = DataAgentContext(
            embedding_repository=self.embedding_repository,
            column_qdrant_repository=self.column_qdrant_repository,
            value_es_repository=self.value_es_repository,
            metric_qdrant_repository=self.metric_qdrant_repository,
            meta_mysql_repository=self.meta_mysql_repository,
            dw_mysql_repository=self.dw_mysql_repository,
        )
        # 初始状态，包含用户输入和对话历史
        state = DataAgentState(query=query, chat_history=chat_history or [])
        try:
            # stream_mode="custom" 让每个节点通过runtime.stream_writer发送自定义JSON
            async with asyncio.timeout(QUERY_TIMEOUT_SECONDS):
                async for chunk in graph.astream(input=state, context=context, stream_mode="custom"):
                    yield f"data: {json.dumps(chunk, ensure_ascii=False, default=str)}\n\n"
        except TimeoutError:
            yield f"data: {json.dumps({'type': 'error', 'message': f'查询超时（{QUERY_TIMEOUT_SECONDS}秒）'}, ensure_ascii=False)}\n\n"
        except Exception as e:
            # 兜底错误处理，确保前端能收到错误信息
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False, default=str)}\n\n"

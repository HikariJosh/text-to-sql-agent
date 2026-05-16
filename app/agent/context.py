from typing import TypedDict

from app.repositories.embedding_repository import EmbeddingRepository
from app.repositories.es.value_repository import ValueRepository
from app.repositories.mysql.dw_repository import DWRepository
from app.repositories.mysql.meta_repository import MetaRepository
from app.repositories.qdrant.column_repository import ColumnRepository
from app.repositories.qdrant.metric_repository import MetricRepository


class DataAgentContext(TypedDict):
    """
    Agent上下文：存放所有外部服务的依赖，通过LangGraph的context参数传递给每个节点
    每个节点通过runtime.context访问这些依赖，无需通过全局变量传递
    """

    embedding_repository: EmbeddingRepository  # 文字转向量的工具

    column_qdrant_repository: ColumnRepository  # 字段向量检索
    metric_qdrant_repository: MetricRepository  # 指标向量检索

    value_es_repository: ValueRepository  # 取值全文检索

    meta_mysql_repository: MetaRepository  # 元数据CRUD
    dw_mysql_repository: DWRepository  # 数仓查询/验证/执行

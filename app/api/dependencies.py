"""
FastAPI依赖注入模块
通过Depends链式注入，把所有外部服务的client/repository组装到QueryService中
- Session级别的依赖(MySQL)：每个请求创建独立的数据库会话，请求结束后自动关闭
- 单例级别的依赖(Qdrant/ES/Embedding)：整个应用共享同一个client实例
"""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

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
from app.services.query_service import QueryService

# ---- Session级别依赖：每个请求创建独立的数据库会话 ----


async def get_meta_session():
    # 使用async with管理session生命周期，请求结束后自动commit/rollback/close
    async with meta_mysql_client_manager.session_factory() as session:
        yield session


async def get_dw_session():
    async with dw_mysql_client_manager.session_factory() as session:
        yield session


# ---- 单例级别依赖：整个应用共享同一个client ----


async def get_embedding_repository():
    return EmbeddingRepository(embedding_client_manager)


async def get_column_qdrant_repository():
    return ColumnRepository(qdrant_client_manager.client)


async def get_value_es_repository():
    return ValueRepository(es_client_manager.client)


async def get_metric_qdrant_repository():
    return MetricRepository(qdrant_client_manager.client)


# ---- Repository级别依赖：注入session到repository ----


async def get_meta_mysql_repository(session: AsyncSession = Depends(get_meta_session)):
    return MetaRepository(session)


async def get_dw_mysql_repository(session: AsyncSession = Depends(get_dw_session)):
    return DWRepository(session)


# ---- 最终组装：把所有依赖注入到QueryService ----


async def get_query_service(
    embedding_repository: EmbeddingRepository = Depends(get_embedding_repository),
    column_qdrant_repository: ColumnRepository = Depends(get_column_qdrant_repository),
    value_es_repository: ValueRepository = Depends(get_value_es_repository),
    metric_qdrant_repository: MetricRepository = Depends(get_metric_qdrant_repository),
    meta_mysql_repository: MetaRepository = Depends(get_meta_mysql_repository),
    dw_mysql_repository: DWRepository = Depends(get_dw_mysql_repository),
) -> QueryService:
    return QueryService(
        embedding_repository=embedding_repository,
        column_qdrant_repository=column_qdrant_repository,
        value_es_repository=value_es_repository,
        metric_qdrant_repository=metric_qdrant_repository,
        meta_mysql_repository=meta_mysql_repository,
        dw_mysql_repository=dw_mysql_repository,
    )

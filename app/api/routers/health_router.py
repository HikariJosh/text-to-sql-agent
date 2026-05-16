"""
健康检查端点：供运维监控和负载均衡器探活使用
"""

from fastapi import APIRouter
from sqlalchemy import text

from app.agent.llm import llm
from app.clients.embedding_client_manager import embedding_client_manager
from app.clients.es_client_manager import es_client_manager
from app.clients.mysql_client_manager import meta_mysql_client_manager
from app.clients.qdrant_client_manager import qdrant_client_manager
from app.repositories.embedding_repository import EmbeddingRepository

health_router = APIRouter(tags=["health"])


@health_router.get("/health")
async def health_check():
    dependencies = {}
    overall_healthy = True

    # 检查 MySQL 连接
    try:
        async with meta_mysql_client_manager.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        dependencies["mysql"] = "healthy"
    except Exception as e:
        dependencies["mysql"] = f"unhealthy: {e}"
        overall_healthy = False

    # 检查 Qdrant 连接
    try:
        await qdrant_client_manager.client.get_collections()
        dependencies["qdrant"] = "healthy"
    except Exception as e:
        dependencies["qdrant"] = f"unhealthy: {e}"
        overall_healthy = False

    # 检查 ES 连接
    try:
        await es_client_manager.client.ping()
        dependencies["elasticsearch"] = "healthy"
    except Exception as e:
        dependencies["elasticsearch"] = f"unhealthy: {e}"
        overall_healthy = False

    # 检查 Embedding 模型 (TEI)
    try:
        await EmbeddingRepository(embedding_client_manager).embed(["test"])
        dependencies["embedding"] = "healthy"
    except Exception as e:
        dependencies["embedding"] = f"unhealthy: {e}"
        overall_healthy = False

    # 检查 LLM 连接
    try:
        llm.invoke("ping")
        dependencies["llm"] = "healthy"
    except Exception as e:
        dependencies["llm"] = f"unhealthy: {e}"
        overall_healthy = False

    return {
        "status": "healthy" if overall_healthy else "unhealthy",
        "dependencies": dependencies,
    }

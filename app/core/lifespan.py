"""
FastAPI生命周期管理：在应用启动时初始化所有外部服务连接，关闭时释放资源
lifespan是一个async context manager，yield之前是启动逻辑，yield之后是关闭逻辑
"""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.clients.embedding_client_manager import embedding_client_manager
from app.clients.es_client_manager import es_client_manager
from app.clients.mysql_client_manager import dw_mysql_client_manager, meta_mysql_client_manager
from app.clients.qdrant_client_manager import qdrant_client_manager

# 活跃请求计数器，用于优雅关闭时等待在途请求完成
_active_requests: int = 0
_shutdown_event = asyncio.Event()

# 优雅关闭等待超时（秒）
DRAIN_TIMEOUT = 60


def increment_active_requests():
    global _active_requests
    _active_requests += 1


def decrement_active_requests():
    global _active_requests
    _active_requests -= 1
    if _active_requests <= 0:
        _shutdown_event.set()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ---- 应用启动：初始化所有客户端连接 ----
    embedding_client_manager.init()  # Embedding是无状态HTTP调用，不需要close
    qdrant_client_manager.init()  # Qdrant长连接
    es_client_manager.init()  # ES长连接
    meta_mysql_client_manager.init()  # meta MySQL连接池
    dw_mysql_client_manager.init()  # dw MySQL连接池
    yield
    # ---- 应用关闭：等待在途请求完成，然后释放连接 ----
    if _active_requests > 0:
        try:
            await asyncio.wait_for(_shutdown_event.wait(), timeout=DRAIN_TIMEOUT)
        except asyncio.TimeoutError:
            pass  # 超时后强制关闭

    await qdrant_client_manager.close()
    await es_client_manager.close()
    await meta_mysql_client_manager.close()
    await dw_mysql_client_manager.close()

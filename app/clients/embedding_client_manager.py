import httpx

from app.conf.app_config import EmbeddingConfig, app_config


class EmbeddingClientManager:
    """Embedding客户端管理器，只负责管理httpx连接的生命周期"""

    def __init__(self, config: EmbeddingConfig):
        self.client: httpx.AsyncClient | None = None
        self.config = config

    @property
    def url(self) -> str:
        return f"http://{self.config.host}:{self.config.port}/embed"

    def init(self):
        self.client = httpx.AsyncClient(timeout=120)

    async def close(self):
        if self.client:
            await self.client.aclose()


# 模块级单例，整个应用共享同一个Embedding客户端实例
embedding_client_manager = EmbeddingClientManager(app_config.embedding)

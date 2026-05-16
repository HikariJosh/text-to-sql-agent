import asyncio
import random

from qdrant_client import AsyncQdrantClient, models

from app.conf.app_config import QdrantConfig, app_config


class QdrantClientManager:
    """
    Qdrant向量数据库客户端管理器，维护一个AsyncQdrantClient长连接
    Qdrant底层是gRPC/HTTP长连接，需要显式close释放资源
    """

    def __init__(self, qdrant_config: QdrantConfig):
        self.qdrant_config = qdrant_config
        self.client: AsyncQdrantClient | None = None

    def _get_url(self):
        return f"http://{self.qdrant_config.host}:{self.qdrant_config.port}"

    def init(self):
        # 创建异步Qdrant客户端，内部维护gRPC/HTTP连接
        self.client = AsyncQdrantClient(url=self._get_url())

    async def close(self):
        # 关闭连接，释放资源
        await self.client.close()


# 模块级单例
qdrant_client_manager = QdrantClientManager(app_config.qdrant)


# 测试代码
if __name__ == "__main__":
    qdrant_client_manager.init()

    async def test():
        client = qdrant_client_manager.client
        if not await client.collection_exists("my_collection"):
            await client.create_collection(
                collection_name="my_collection",
                vectors_config=models.VectorParams(size=10, distance=models.Distance.COSINE),
            )

        await client.upsert(
            collection_name="my_collection",
            points=[
                models.PointStruct(
                    id=i,
                    vector=[random.random() for _ in range(10)],
                )
                for i in range(100)
            ],
        )

        res = await client.query_points(
            collection_name="my_collection",
            query=[random.random() for _ in range(10)],  # type: ignore
            limit=10,
            score_threshold=0.8,
        )

        print(res)

    asyncio.run(test())

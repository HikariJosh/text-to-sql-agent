from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from app.conf.app_config import app_config
from app.meta.entities.metric_info import MetricInfo


class MetricRepository:
    """
    指标向量检索仓库：负责指标信息的向量存储和相似度检索
    和ColumnRepository结构一致，只是操作的collection和返回的实体类型不同
    """

    collection_name = "metric_info_collection"

    def __init__(self, client: AsyncQdrantClient):
        self.client = client

    async def ensure_collection(self):
        """确保collection存在，不存在则创建"""
        if not await self.client.collection_exists(self.collection_name):
            await self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=app_config.qdrant.embedding_size, distance=Distance.COSINE),
            )

    async def clear(self):
        """清空collection中的所有数据，构建前调用确保数据一致性"""
        if await self.client.collection_exists(self.collection_name):
            await self.client.delete_collection(self.collection_name)
            await self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=app_config.qdrant.embedding_size, distance=Distance.COSINE),
            )

    async def upsert(self, ids: list[str], embeddings: list[list[float]], payloads: list[dict], batch_size: int = 20):
        """批量写入向量数据，分批次避免请求过大"""
        points: list[PointStruct] = [
            PointStruct(id=id, vector=embedding, payload=payload)
            for id, embedding, payload in zip(ids, embeddings, payloads)
        ]

        for i in range(0, len(points), batch_size):
            await self.client.upsert(collection_name=self.collection_name, points=points[i : i + batch_size])

    async def search(
        self, embeded_keyword: list[float], score_threshold: float = 0.6, limit: int = 20
    ) -> list[MetricInfo]:
        """向量相似度检索，返回和关键词向量距离较近的指标信息"""
        result = await self.client.query_points(
            collection_name=self.collection_name,
            query=embeded_keyword,
            limit=limit,
            score_threshold=score_threshold,  # 余弦相似度阈值，越高召回越严格
        )
        return [MetricInfo(**point.payload) for point in result.points]

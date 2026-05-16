from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from app.conf.app_config import app_config
from app.meta.entities.column_info import ColumnInfo


class ColumnRepository:
    """
    字段向量检索仓库：负责字段信息的向量存储和相似度检索
    每个字段的name、description、alias都会分别建立一条向量记录，
    这样无论用户用哪种方式描述，都能召回对应的字段
    """

    collection_name = "column_info_collection"

    def __init__(self, client: AsyncQdrantClient):
        self.client = client

    async def ensure_collection(self):
        """确保collection存在，不存在则创建。size取决于Embedding的维度，distance取决于Embedding的类型"""
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

        for i in range(0, len(points), batch_size):  # 分批次插入，避免一次插入过多数据导致请求过大
            await self.client.upsert(collection_name=self.collection_name, points=points[i : i + batch_size])

    async def search(
        self, embeded_keyword: list[float], score_threshold: float = 0.6, limit: int = 20
    ) -> list[ColumnInfo]:
        """向量相似度检索，返回和关键词向量距离较近的字段信息"""
        result = await self.client.query_points(
            collection_name=self.collection_name,
            query=embeded_keyword,
            limit=limit,
            score_threshold=score_threshold,  # 余弦相似度阈值，越高召回越严格
        )
        return [ColumnInfo(**point.payload) for point in result.points]

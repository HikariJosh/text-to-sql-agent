from app.clients.embedding_client_manager import EmbeddingClientManager


class EmbeddingRepository:
    """向量化仓库：封装TEI的/embed接口调用，支持分批请求"""

    def __init__(self, client_manager: EmbeddingClientManager, batch_size: int = 32):
        self.client_manager = client_manager
        self.batch_size = batch_size

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """批量向量化：自动分批调用TEI（TEI限制单次最多batch_size条）"""
        all_embeddings: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            resp = await self.client_manager.client.post(self.client_manager.url, json={"inputs": batch})
            resp.raise_for_status()
            all_embeddings.extend(resp.json())
        return all_embeddings

    async def embed_single(self, text: str) -> list[float]:
        """单条向量化"""
        result = await self.embed([text])
        return result[0]

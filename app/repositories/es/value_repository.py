from dataclasses import asdict

from elasticsearch import AsyncElasticsearch

from app.meta.entities.value_info import ValueInfo


class ValueRepository:
    """
    字段取值的ES仓库：负责维度字段取值的全文检索
    例如用户输入"华北"，能在ES中匹配到region字段的取值"华北地区"
    使用IK分词器，适合中文全文检索
    """

    index_name = "value_index"
    # 索引映射：value字段使用IK分词器做中文全文检索，id和column_id用keyword精确匹配
    index_mapping = {
        "dynamic": False,
        "properties": {
            "id": {"type": "keyword"},
            "value": {
                "type": "text",
                "analyzer": "ik_max_word",  # 索引时用ik_max_word最大化分词
                "search_analyzer": "ik_max_word",  # 搜索时也用ik_max_word
            },
            "column_id": {"type": "keyword"},
        },
    }

    def __init__(self, client: AsyncElasticsearch):
        self.client = client

    async def ensure_index(self):
        """如果index不存在则创建index"""
        if not await self.client.indices.exists(index=self.index_name):
            body = {"mappings": self.index_mapping}
            await self.client.indices.create(index=self.index_name, body=body)

    async def clear(self):
        """清空index中的所有数据，构建前调用确保数据一致性"""
        if await self.client.indices.exists(index=self.index_name):
            await self.client.delete_by_query(index=self.index_name, query={"match_all": {}})

    async def index(self, value_infos: list[ValueInfo], batch_size: int = 20):
        """批量写入取值数据到ES，使用bulk API提高写入效率，相同id会覆盖而非新增"""
        for i in range(0, len(value_infos), batch_size):
            batch_value_infos = value_infos[i : i + batch_size]
            # bulk API格式：每两条为一组，第一条是操作元数据，第二条是实际数据
            batch_operations = []
            for value_info in batch_value_infos:
                batch_operations.append({"index": {"_index": self.index_name, "_id": value_info.id}})
                batch_operations.append(asdict(value_info))

            await self.client.bulk(operations=batch_operations)

    async def search(self, keyword: str, threshold_score: float = 0.6, size: int = 20) -> list[ValueInfo]:
        """全文检索字段取值，返回匹配度高于阈值的结果"""
        response = await self.client.search(
            index=self.index_name,
            query={
                "match": {
                    "value": keyword,
                }
            },
            size=size,
            min_score=threshold_score,  # 最低匹配分数，可以调整召回的严格程度
        )
        return [ValueInfo(**hit["_source"]) for hit in response["hits"]["hits"]]

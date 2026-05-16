import asyncio

from elasticsearch import AsyncElasticsearch

from app.conf.app_config import ESConfig, app_config


class ESClientManager:
    """
    Elasticsearch客户端管理器，维护一个AsyncElasticsearch长连接
    ES底层是TCP连接，需要显式close释放资源
    """

    def __init__(self, es_config: ESConfig):
        self.es_config = es_config
        self.client: AsyncElasticsearch | None = None

    def _get_url(self):
        return f"http://{self.es_config.host}:{self.es_config.port}"

    def init(self):
        # 创建异步ES客户端，内部维护HTTP连接池
        self.client = AsyncElasticsearch(hosts=[self._get_url()])

    async def close(self):
        # 关闭连接池，释放TCP连接资源
        await self.client.close()


# 模块级单例
es_client_manager = ESClientManager(app_config.es)


# 测试代码
if __name__ == "__main__":
    es_client_manager.init()

    async def test():
        client = es_client_manager.client

        # 创建索引
        await client.indices.create(
            index="my-books",
            mappings={
                "dynamic": False,
                "properties": {
                    "name": {"type": "text"},
                    "author": {"type": "text"},
                    "release_date": {"type": "date", "format": "yyyy-MM-dd"},
                    "page_count": {"type": "integer"},
                },
            },
        )

        # 插入数据
        await client.bulk(
            operations=[
                {"index": {"_index": "my-books"}},
                {
                    "name": "Revelation Space",
                    "author": "Alastair Reynolds",
                    "release_date": "2000-03-15",
                    "page_count": 585,
                },
                {"index": {"_index": "my-books"}},
                {"name": "1984", "author": "George Orwell", "release_date": "1985-06-01", "page_count": 328},
                {"index": {"_index": "my-books"}},
                {"name": "Fahrenheit 451", "author": "Ray Bradbury", "release_date": "1953-10-15", "page_count": 227},
                {"index": {"_index": "my-books"}},
                {"name": "Brave New World", "author": "Aldous Huxley", "release_date": "1932-06-01", "page_count": 268},
                {"index": {"_index": "my-books"}},
                {
                    "name": "The Handmaids Tale",
                    "author": "Margaret Atwood",
                    "release_date": "1985-06-01",
                    "page_count": 311,
                },
            ],
        )

        # 搜索
        resp = await client.search(
            index="my-books",
            query={"match": {"name": "brave"}},
        )
        print(resp)
        await es_client_manager.close()

    asyncio.run(test())

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.conf.app_config import DBConfig, app_config


class MysqlClientManager:
    def __init__(self, db_config: DBConfig):
        self.db_config = db_config
        # class DBConfig:
        # host: str
        # port: int
        # user: str
        # password: str
        # database: str
        self.engine: AsyncEngine | None = None  # 创造异步egine(打通连接的桥梁)，初始值为None
        self.session_factory = None

    def _get_url(self):
        return f"mysql+asyncmy://{self.db_config.user}:{self.db_config.password}@{self.db_config.host}:{self.db_config.port}/{self.db_config.database}?charset=utf8mb4"

    def init(self):
        self.engine = create_async_engine(url=self._get_url(), pool_size=10, pool_pre_ping=True)
        # 创建异步引擎，设置连接池大小为10，并启用连接预检测功能，以确保连接的有效性
        self.session_factory = async_sessionmaker(self.engine, autoflush=True, expire_on_commit=False, autobegin=True)
        # 创建异步会话工厂，配置自动刷新、提交后不失效和自动开始事务的选项，以便于管理数据库会话

    async def close(self):
        await self.engine.dispose()


# 初始化 MySQL 客户端管理器实例,分别用于元数据库和数据仓库的连接管理,可直接全局调用
dw_mysql_client_manager = MysqlClientManager(app_config.db_dw)
meta_mysql_client_manager = MysqlClientManager(app_config.db_meta)


# 测试代码
if __name__ == "__main__":
    meta_mysql_client_manager.init()

    async def test():
        async with meta_mysql_client_manager.session_factory() as session:
            result = await session.execute(text("select * from table_info limit 10"))
            rows = result.fetchall()
            print(rows)

    asyncio.run(test())

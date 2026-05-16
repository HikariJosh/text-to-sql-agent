"""
从业务配置构建 Meta 知识库。

读取 conf/meta_config/ 下的 table_column_info.yaml 和 metric_info.yaml，
将表结构写入元数据库，列值同步到 Elasticsearch，向量嵌入存入 Qdrant。

用法:
    uv run python -m app.scripts.build_meta_knowledge -c conf/meta_config/table_column_info.yaml -c conf/meta_config/metric_info.yaml
"""

import argparse
import asyncio
from pathlib import Path

from app.clients.embedding_client_manager import embedding_client_manager
from app.clients.es_client_manager import es_client_manager
from app.clients.mysql_client_manager import dw_mysql_client_manager, meta_mysql_client_manager
from app.clients.qdrant_client_manager import qdrant_client_manager
from app.meta.orm import (  # noqa: F401 - 确保 ORM 模型被注册到 Base.metadata
    column_info_orm,
    metric_column_orm,
    metric_info_orm,
    table_info_orm,
)
from app.meta.orm.base import Base
from app.repositories.embedding_repository import EmbeddingRepository
from app.repositories.es.value_repository import ValueRepository
from app.repositories.mysql.dw_repository import DWRepository
from app.repositories.mysql.meta_repository import MetaRepository
from app.repositories.qdrant.column_repository import ColumnRepository
from app.repositories.qdrant.metric_repository import MetricRepository
from app.services.meta_knowledge_service import MetaKnowledgeService


async def build(config_paths: list[Path]):
    meta_mysql_client_manager.init()
    dw_mysql_client_manager.init()
    qdrant_client_manager.init()
    embedding_client_manager.init()
    es_client_manager.init()

    # 自动建表：如果 meta 库中表不存在则创建，已存在则跳过
    async with meta_mysql_client_manager.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        async with (
            meta_mysql_client_manager.session_factory() as meta_session,
            dw_mysql_client_manager.session_factory() as dw_session,
        ):
            meta_knowledge_service = MetaKnowledgeService(
                meta_mysql_repository=MetaRepository(meta_session),
                dw_mysql_repository=DWRepository(dw_session),
                column_qdrant_repository=ColumnRepository(qdrant_client_manager.client),
                metric_qdrant_repository=MetricRepository(qdrant_client_manager.client),
                embedding_repository=EmbeddingRepository(embedding_client_manager),
                value_es_repository=ValueRepository(es_client_manager.client),
            )

            for path in config_paths:
                await meta_knowledge_service.build(path)
    finally:
        await meta_mysql_client_manager.close()
        await dw_mysql_client_manager.close()
        await qdrant_client_manager.close()
        await es_client_manager.close()


def main():
    parser = argparse.ArgumentParser(description="从业务配置构建 Meta 知识库")
    parser.add_argument(
        "-c",
        "--config",
        dest="configs",
        type=Path,
        action="append",
        required=True,
        help="配置文件路径，可多次指定（如 -c tables_info.yaml -c metrics_info.yaml）",
    )
    args = parser.parse_args()
    asyncio.run(build(args.configs))


if __name__ == "__main__":
    main()

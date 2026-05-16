"""
MetaKnowledgeService - 元数据知识库构建服务

核心职责：
    将 YAML 配置文件中的业务元数据，经过"配置→实体→存储"三层转换，
    同步到 MySQL、Qdrant、Elasticsearch 三种存储中，供在线查询时检索使用。

数据流转：
    YAML 配置文件 (conf/meta_config/)
        ↓  OmegaConf 加载 + MetaConfig schema 校验
    MetaConfig 对象 (app/conf/meta_config.py)
        ↓  业务逻辑：补充 id、type、examples 等运行时字段
    Entity 实体对象 (app/meta/entities/)
        ↓  Mapper 转换：to_model()
    ORM 模型 (app/meta/orm/)
        ↓  SQLAlchemy
    MySQL 表

三层对象的字段差异（以 ColumnConfig / ColumnInfo / ColumnInfoORM 为例）：
    ┌─────────────┬──────────────┬──────────────┬────────────────┐
    │ 字段        │ ColumnConfig │ ColumnInfo   │ ColumnInfoORM  │
    ├─────────────┼──────────────┼──────────────┼────────────────┤
    │ name        │ str          │ str          │ String(128)    │
    │ role        │ str          │ str          │ String(32)     │
    │ description │ str          │ str          │ Text           │
    │ alias       │ list[str]    │ list[str]    │ JSON           │
    │ sync        │ bool         │ -            │ -              │
    │ id          │ -            │ str          │ String(64) PK  │
    │ type        │ -            │ str          │ String(64)     │
    │ examples    │ -            │ list[Any]    │ JSON           │
    │ table_id    │ -            │ str          │ String(64)     │
    └─────────────┴──────────────┴──────────────┴────────────────┘

    - MetaConfig 只含 YAML 中用户手写的字段（最小配置）
    - Entity 多出的字段（id/type/examples/table_id）由构建时从数据仓库查询生成
    - sync 字段仅在构建时决定是否同步到 ES，无需持久化

三种存储的用途：
    ┌─────────────────┬──────────────────────────────────────────────┐
    │ 存储            │ 用途                                         │
    ├─────────────────┼──────────────────────────────────────────────┤
    │ MySQL (meta库)  │ 结构化存储：表/字段/指标元信息，关联关系       │
    │ Qdrant          │ 向量检索：字段名/描述/别名、指标名/描述/别名   │
    │ Elasticsearch   │ 全文检索：维度字段的实际取值（如"北京市"）     │
    └─────────────────┴──────────────────────────────────────────────┘

构建入口：
    uv run python -m app.scripts.build_meta_knowledge \
        -c conf/meta_config/table_column_info.yaml \
        -c conf/meta_config/metric_info.yaml
"""

from dataclasses import asdict
from pathlib import Path
from uuid import UUID, uuid5

from loguru import logger
from omegaconf import OmegaConf

from app.conf.meta_config import MetaConfig
from app.meta.entities.column_info import ColumnInfo
from app.meta.entities.metric_column import MetricColumn
from app.meta.entities.metric_info import MetricInfo
from app.meta.entities.table_info import TableInfo
from app.meta.entities.value_info import ValueInfo
from app.repositories.embedding_repository import EmbeddingRepository
from app.repositories.es.value_repository import ValueRepository
from app.repositories.mysql.dw_repository import DWRepository
from app.repositories.mysql.meta_repository import MetaRepository
from app.repositories.qdrant.column_repository import ColumnRepository
from app.repositories.qdrant.metric_repository import MetricRepository

# UUID5 namespace for deterministic point IDs (same string → same UUID)
_QDRANT_NS = UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")


class MetaKnowledgeService:
    def __init__(
        self,
        meta_mysql_repository: MetaRepository,
        dw_mysql_repository: DWRepository,
        column_qdrant_repository: ColumnRepository,
        metric_qdrant_repository: MetricRepository,
        value_es_repository: ValueRepository,
        embedding_repository: EmbeddingRepository,
    ):
        """
        初始化MetaKnowledgeService实例，注入所需的数据库仓库和客户端管理器。
        :param meta_mysql_repository: 用于操作Meta数据库的仓库实例
        :param dw_mysql_repository: 用于操作数据仓库的仓库实例
        :param column_qdrant_repository: 用于操作Qdrant中列信息的仓库实例
        :param metric_qdrant_repository: 用于操作Qdrant中指标信息的仓库实例
        :param value_es_repository: 用于操作Elasticsearch中值信息的仓库实例
        :param embedding_client_manager: 用于获取向量化客户端的管理器实例
        """
        self.meta_mysql_repository: MetaRepository = meta_mysql_repository
        self.dw_mysql_repository: DWRepository = dw_mysql_repository

        self.column_qdrant_repository: ColumnRepository = column_qdrant_repository
        self.metric_qdrant_repository: MetricRepository = metric_qdrant_repository

        self.value_es_repository: ValueRepository = value_es_repository

        self.embedding_repository = embedding_repository

    async def _embed_texts(self, texts: list[str]) -> list[list[float]]:
        """调用TEI容器做批量向量化"""
        return await self.embedding_repository.embed(texts)

    async def _save_table_to_meta(self, meta_config: MetaConfig) -> list[ColumnInfo]:
        """
        同时存了tales_infos和columns两张表，保证数据一致性
        根据MetaConfig中的表信息，同步表结构和字段信息到Meta数据库中。
        1. 从数据仓库中查询每个表的字段类型和示例值。
        2. 将表信息和字段信息保存到Meta数据库中。
        3. 返回字段信息列表，供后续建立向量索引和全文索引使用。
        """
        table_infos: list[TableInfo] = []
        column_infos: list[ColumnInfo] = []

        for table in meta_config.tables:
            # table: TableConfig —> table_info: TableInfo
            table_info = TableInfo(
                id=table.name,
                name=table.name,
                role=table.role,
                description=table.description,
            )
            table_infos.append(table_info)

            # 查询字段类型
            column_types = await self.dw_mysql_repository.get_column_types(table.name)
            for column in table.columns:
                # column: ColumnConfig —> column_info: ColumnInfo
                column_values = await self.dw_mysql_repository.get_column_values(
                    table.name,
                    column.name,
                )  # 获取字段的example，供后续存储和向量化使用. get_column_values -> list[dict]
                column_info = ColumnInfo(
                    id=f"{table.name}.{column.name}",
                    name=column.name,
                    type=column_types.get(column.name),
                    role=column.role,
                    examples=column_values,
                    description=column.description,
                    alias=column.alias,
                    table_id=table.name,
                )
                column_infos.append(column_info)

        async with self.meta_mysql_repository.session.begin():
            await self.meta_mysql_repository.save_table_infos(table_infos)
            await self.meta_mysql_repository.save_column_infos(column_infos)
        return column_infos  # 返回column_infos，后续建立向量索引和全文索引需要用到字段的文本信息和id信息(_save_columns_to_qdrant, _save_values_to_es)

    async def _save_columns_to_qdrant(self, column_infos: list[ColumnInfo]):
        await self.column_qdrant_repository.ensure_collection()
        """
        e.g.
        id                  | Name     | Type        | Role      | Examples                    | Description | Alias            | Table_id
        dim_region.province | province | varchar(30) | dimension | ["北京市", "上海市", "广东省"] | 省份维度      | ["省份", "省"] | dim_region
        把这一条的name、description、alias这些文本信息都拿来做embedding，建立向量索引，方便后续的相似度搜索
        分别建立point(也就是id和vector是不一样的),payload是一样的
        """
        points: list[dict] = []  # id, vector(这里先拿text,到时候批量再向量化), payload
        for column_info in column_infos:
            points.append(
                {
                    "id": str(uuid5(_QDRANT_NS, f"{column_info.id}.name")),
                    "embedding_text": column_info.name,
                    "payload": asdict(column_info),
                }
            )

            points.append(
                {
                    "id": str(uuid5(_QDRANT_NS, f"{column_info.id}.description")),
                    "embedding_text": column_info.description,
                    "payload": asdict(column_info),
                }
            )

            for idx, alia in enumerate(column_info.alias):
                points.append(
                    {
                        "id": str(uuid5(_QDRANT_NS, f"{column_info.id}.alias.{idx}")),
                        "embedding_text": alia,
                        "payload": asdict(column_info),
                    }
                )
            # 向量化
        embedding_texts = [point["embedding_text"] for point in points]
        embeddings = await self._embed_texts(embedding_texts)

        ids = [point["id"] for point in points]
        payloads = [point["payload"] for point in points]

        await self.column_qdrant_repository.upsert(ids, embeddings, payloads)

    async def _save_values_to_es(self, meta_config: MetaConfig):
        """
        把db库内所有table的每个column(field)的value都拿出来做embedding，
        建立全文索引，方便后续的基于value的搜索
        """
        await self.value_es_repository.ensure_index()
        values_infos: list[ValueInfo] = []
        for table in meta_config.tables:
            for column in table.columns:
                if column.sync:
                    # 如果sync是true，说明这个字段需要同步到es中建立全文索引
                    current_column_domains = await self.dw_mysql_repository.get_column_values(
                        table.name,
                        column.name,
                        limit=10**9,  # 近似全量，避免传入浮点值
                    )
                    current_values_info = [
                        ValueInfo(
                            id=f"{table.name}.{column.name}.{value}",
                            value=value,
                            column_id=f"{table.name}.{column.name}",
                        )
                        for value in current_column_domains
                    ]
                    values_infos.extend(current_values_info)

        await self.value_es_repository.index(values_infos)
        # 往es中批量插入数据，用的是index,这里沿用这个叫法，虽然它也可以叫upsert，但index更符合es的语义

    async def _save_metrics_to_meta(self, meta_config: MetaConfig) -> list[MetricInfo]:
        metric_infos: list[MetricInfo] = []
        metric_columns: list[MetricColumn] = []
        for metric in meta_config.metrics:
            # metric: MetricConfig —> metric_info: MetricInfo
            metric_info = MetricInfo(
                id=metric.name,
                name=metric.name,
                description=metric.description,
                relevant_columns=metric.relevant_columns,
                formula=metric.formula,
                alias=metric.alias,
            )
            metric_infos.append(metric_info)
            for relevant_column in metric.relevant_columns:
                # relevant_column: str —> metric_column: MetricColumn
                metric_column = MetricColumn(
                    column_id=relevant_column,
                    metric_id=metric.name,
                )
                metric_columns.append(metric_column)
        async with self.meta_mysql_repository.session.begin():
            await self.meta_mysql_repository.save_metric_infos(metric_infos)
            await self.meta_mysql_repository.save_metric_columns(metric_columns)

        return metric_infos

    async def _save_metrics_to_qdrant(self, metric_infos: list[MetricInfo]):
        await self.metric_qdrant_repository.ensure_collection()
        points: list[dict] = []
        for metric_info in metric_infos:
            points.append(
                {
                    "id": str(uuid5(_QDRANT_NS, f"{metric_info.id}.name")),
                    "embedding_text": metric_info.name,
                    "payload": asdict(metric_info),
                }
            )

            points.append(
                {
                    "id": str(uuid5(_QDRANT_NS, f"{metric_info.id}.description")),
                    "embedding_text": metric_info.description,
                    "payload": asdict(metric_info),
                }
            )

            for idx, alia in enumerate(metric_info.alias):
                points.append(
                    {
                        "id": str(uuid5(_QDRANT_NS, f"{metric_info.id}.alias.{idx}")),
                        "embedding_text": alia,
                        "payload": asdict(metric_info),
                    }
                )
        # 向量化
        embedding_texts = [point["embedding_text"] for point in points]
        embeddings = await self._embed_texts(embedding_texts)

        ids = [point["id"] for point in points]
        payloads = [point["payload"] for point in points]

        await self.metric_qdrant_repository.upsert(ids, embeddings, payloads)

    async def build(self, config_path: Path):
        # 1. 读取配置文件
        content = OmegaConf.load(config_path)
        schema = OmegaConf.structured(MetaConfig)
        merged = OmegaConf.merge(schema, content)
        meta_config: MetaConfig = OmegaConf.to_object(merged)
        logger.info("✅成功加载配置文件，准备构建Meta知识库")

        # 2. 根据业务配置同步表信息(tables)和指标信息(metrics)
        if meta_config.tables:
            # 2.1 清空旧数据，确保表名/列名变更后数据一致
            await self.column_qdrant_repository.clear()
            await self.value_es_repository.clear()
            logger.info("✅清空旧的向量索引和全文索引")

            # 2.2 将表信息和字段信息保存meta数据库中
            column_infos = await self._save_table_to_meta(meta_config)
            logger.info("✅成功保存表信息和字段信息到数据库")

            # 2.3 对字段信息建立向量索引
            await self._save_columns_to_qdrant(column_infos)
            logger.info("✅成功向量化字段信息(name, description, alias)到qdrant")

            # 2.4 对指定的维度字段建立全文索引
            await self._save_values_to_es(meta_config)
            logger.info("✅成功为字段的value建立全文索引")

        # 3. 根据yaml文件同步指定的指标信息
        if meta_config.metrics:
            # 3.1 清空旧的指标向量索引
            await self.metric_qdrant_repository.clear()
            logger.info("✅清空旧的指标向量索引")

            # 3.2 将指标信息保存meta数据库中
            metric_infos = await self._save_metrics_to_meta(meta_config)
            logger.info("✅成功保存指标信息到数据库")

            # 3.3 对指标的维度字段建立向量索引
            await self._save_metrics_to_qdrant(metric_infos)
            logger.info("✅成功向量化指标信息")

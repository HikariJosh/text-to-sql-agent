"""
Meta Repository：负责与meta数据库交互

meta库是元数据库，存储数据仓库的表结构信息（表、字段、指标），
是agent召回和过滤的数据基础。

表结构：
  - table_info: 表信息（id, name, role, description）
  - column_info: 字段信息（id, name, type, role, examples, description, alias, table_id）
  - metric_info: 指标信息（id, name, description, relevant_columns, alias）
  - metric_column: 指标-字段关联关系

职责边界：
  - Repository层只负责数据库CRUD，不包含业务逻辑
  - save方法实现entity → orm的转换（写入时）
  - get方法实现orm → entity的转换（读取时）
  - 确保service层只依赖entity层，不依赖orm层
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.meta.entities.column_info import ColumnInfo
from app.meta.entities.metric_column import MetricColumn
from app.meta.entities.metric_info import MetricInfo
from app.meta.entities.table_info import TableInfo
from app.meta.mappers import column_info, metric_column, metric_info, table_info
from app.meta.orm.column_info_orm import ColumnInfoORM
from app.meta.orm.table_info_orm import TableInfoORM


class MetaRepository:
    """
    负责与meta数据库交互，提供表信息、字段信息、指标信息的增删改查接口，以及字段-指标关联关系的管理接口
    save方法实现entity -> orm的转换，
    get方法实现orm -> entity的转换，
    确保service层只依赖于entity层不依赖于orm层
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def save_table_infos(self, table_infos: list[TableInfo]):
        """保存表信息到meta库，merge会自动判断：主键不存在则insert，已存在则update"""
        for info in table_infos:
            await self.session.merge(table_info.to_orm(info))

    async def save_column_infos(self, column_infos: list[ColumnInfo]):
        """保存字段信息到meta库，merge代替add_all避免主键冲突"""
        for info in column_infos:
            await self.session.merge(column_info.to_orm(info))

    async def save_metric_infos(self, metric_infos: list[MetricInfo]):
        """保存指标信息到meta库"""
        for info in metric_infos:
            await self.session.merge(metric_info.to_orm(info))

    async def save_metric_columns(self, metric_columns: list[MetricColumn]):
        """保存指标-字段关联关系到meta库"""
        for info in metric_columns:
            await self.session.merge(metric_column.to_orm(info))

    async def get_column_info_by_id(self, column_id: str) -> ColumnInfo:
        """根据字段id查询字段信息"""
        result: ColumnInfoORM | None = await self.session.get(ColumnInfoORM, column_id)
        if result:
            return column_info.to_entity(result)
        else:
            raise ValueError(f"Column with id {column_id} not found")

    async def get_table_info_by_id(self, table_id: str) -> TableInfo:
        """根据表id查询表信息"""
        result: TableInfoORM | None = await self.session.get(TableInfoORM, table_id)
        if result:
            return table_info.to_entity(result)
        else:
            raise ValueError(f"Table with id {table_id} not found")

    async def get_all_table_infos(self) -> list[TableInfo]:
        """
        查询所有表信息
        用于 /api/suggestions 接口，获取完整的表列表供LLM生成提示问题
        返回table_info表中的所有记录，映射为TableInfo实体列表
        """
        result = await self.session.execute(text("SELECT * FROM table_info"))
        return [
            TableInfo(id=r.id, name=r.name, role=r.role, description=r.description)
            for r in result
        ]

    async def get_columns_by_table_id(self, table_id: str) -> list[ColumnInfo]:
        """
        查询指定表的所有字段信息
        用于 /api/suggestions 接口，获取每张表的字段列表，
        格式化后传给LLM，让LLM了解数据结构以生成准确的提示问题
        参数化查询（:tid）防止SQL注入
        """
        result = await self.session.execute(
            text("SELECT * FROM column_info WHERE table_id = :tid"),
            {"tid": table_id},
        )
        return [
            ColumnInfo(
                id=r.id, name=r.name, type=r.type, role=r.role,
                examples=r.examples, description=r.description,
                alias=r.alias, table_id=r.table_id,
            )
            for r in result
        ]

    async def get_key_columns_by_table_id(self, table_id: str) -> list[ColumnInfo]:
        """查询指定表的主键和外键字段，用于强制补充到召回结果中确保可以JOIN"""
        sql = """SELECT * FROM column_info
                WHERE table_id = :table_id
                AND role IN ('primary_key', 'foreign_key')
                """
        result = await self.session.execute(text(sql), {"table_id": table_id})
        key_column_infos: list[ColumnInfo] = []
        for record in result:
            column_info = ColumnInfo(
                id=record.id,
                name=record.name,
                type=record.type,
                role=record.role,
                examples=record.examples,
                description=record.description,
                alias=record.alias,
                table_id=record.table_id,
            )
            key_column_infos.append(column_info)
        return key_column_infos

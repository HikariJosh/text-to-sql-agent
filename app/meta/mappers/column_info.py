from dataclasses import asdict

from app.meta.entities.column_info import ColumnInfo
from app.meta.orm.column_info_orm import ColumnInfoORM


def to_entity(model: ColumnInfoORM) -> ColumnInfo:
    return ColumnInfo(
        id=model.id,
        name=model.name,
        type=model.type,
        role=model.role,
        examples=model.examples,
        description=model.description,
        alias=model.alias,
        table_id=model.table_id,
    )


def to_orm(entity: ColumnInfo) -> ColumnInfoORM:
    return ColumnInfoORM(**asdict(entity))

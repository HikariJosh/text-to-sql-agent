from dataclasses import asdict

from app.meta.entities.table_info import TableInfo
from app.meta.orm.table_info_orm import TableInfoORM


def to_entity(model: TableInfoORM) -> TableInfo:
    return TableInfo(
        id=model.id,
        name=model.name,
        role=model.role,
        description=model.description,
    )


def to_orm(entity: TableInfo) -> TableInfoORM:
    return TableInfoORM(**asdict(entity))

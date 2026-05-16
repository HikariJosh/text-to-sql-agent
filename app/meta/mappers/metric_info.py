from dataclasses import asdict

from app.meta.entities.metric_info import MetricInfo
from app.meta.orm.metric_info_orm import MetricInfoORM


def to_entity(model: MetricInfoORM) -> MetricInfo:
    return MetricInfo(
        id=model.id,
        name=model.name,
        description=model.description,
        relevant_columns=model.relevant_columns,
        formula=model.formula,
        alias=model.alias,
    )


def to_orm(entity: MetricInfo) -> MetricInfoORM:
    return MetricInfoORM(**asdict(entity))

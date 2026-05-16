from dataclasses import asdict

from app.meta.entities.metric_column import MetricColumn
from app.meta.orm.metric_column_orm import MetricColumnORM


def to_entity(model: MetricColumnORM) -> MetricColumn:
    return MetricColumn(
        column_id=model.column_id,
        metric_id=model.metric_id,
    )


def to_orm(entity: MetricColumn) -> MetricColumnORM:
    return MetricColumnORM(**asdict(entity))

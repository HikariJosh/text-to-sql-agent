from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.state import ColumnInfoState, DataAgentState, MetricInfoState, TableInfoState
from app.core.log import logger
from app.meta.entities.column_info import ColumnInfo
from app.meta.entities.table_info import TableInfo


async def merge_retrieved_info(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """
    合并召回信息：将3路召回的结果(字段、取值、指标)整合成结构化的表信息和指标信息
    核心逻辑：
    1. 将指标关联的字段补充到字段列表中
    2. 将召回的取值作为examples附加到对应字段上
    3. 按table_id分组，补充主外键(确保可以JOIN)
    4. 转换为LLM可理解的TableInfoState和MetricInfoState格式
    """
    writer = runtime.stream_writer
    writer({"type": "progress", "step": "合并召回信息", "status": "running"})

    # 已召回信息
    retrieved_columns = state["retrieved_columns"]
    retrieved_values = state.get("retrieved_values", [])  # 如果没有就使用空列表
    retrieved_metrics = state.get("retrieved_metrics", [])  # 如果没有就使用空列表

    # 获取所需依赖
    meta_mysql_repository = runtime.context["meta_mysql_repository"]

    # 用字典去重，key为column_id
    retrieved_columns_map: dict[str, ColumnInfo] = {
        retrieved_column.id: retrieved_column for retrieved_column in retrieved_columns
    }

    table_infos: list[TableInfoState] = []

    try:
        # 1. 将指标信息的相关字段加入字段信息列表
        # 例如召回了"销售总额"指标，它的relevant_columns包含"order_amount"，需要补充进来
        for retrieved_metric in retrieved_metrics:
            relevant_columns = retrieved_metric.relevant_columns
            for relevant_column in relevant_columns:
                if relevant_column not in retrieved_columns_map:
                    column_info = await meta_mysql_repository.get_column_info_by_id(relevant_column)
                    retrieved_columns_map[relevant_column] = column_info

        # 2. 将字段取值合并到字段信息列表
        # 例如召回了"华北"这个取值，它属于"region"字段，需要把"华北"加到region的examples里
        for retrieved_value in retrieved_values:
            column_id = retrieved_value.column_id
            column_value = retrieved_value.value
            if column_id not in retrieved_columns_map:
                column_info = await meta_mysql_repository.get_column_info_by_id(column_id)
                retrieved_columns_map[column_id] = column_info
            if column_value not in retrieved_columns_map[column_id].examples:
                retrieved_columns_map[column_id].examples.append(column_value)

        # 3. 按照字段所属的表id进行分组，得到table_id->columns映射
        table_to_columns_map: dict[str, list[ColumnInfo]] = {}
        for column in retrieved_columns_map.values():
            table_id = column.table_id
            if table_id not in table_to_columns_map:
                table_to_columns_map[table_id] = []
            table_to_columns_map[table_id].append(column)

        # 4. 强制添加每个表的主外键
        # 避免因为主外键没有被召回而导致表信息不完整，影响后续JOIN操作
        for table_id in table_to_columns_map.keys():
            key_columns: list[ColumnInfo] = await meta_mysql_repository.get_key_columns_by_table_id(table_id)

            column_ids = [column.id for column in table_to_columns_map[table_id]]
            for key_column in key_columns:
                if key_column.id not in column_ids:
                    table_to_columns_map[table_id].append(key_column)

        # 5. 将table_id->columns映射 转换为 list[TableInfoState]
        for table_id, columns in table_to_columns_map.items():
            table: TableInfo = await meta_mysql_repository.get_table_info_by_id(table_id)
            columns = [
                ColumnInfoState(
                    name=column.name,
                    type=column.type,
                    role=column.role,
                    examples=column.examples,
                    description=column.description,
                    alias=column.alias,
                )
                for column in columns
            ]
            table_info_state = TableInfoState(
                name=table.name, role=table.role, description=table.description, columns=columns
            )
            table_infos.append(table_info_state)

        # 6. 处理指标信息，转换为MetricInfoState格式
        metric_infos: list[MetricInfoState] = [
            MetricInfoState(
                name=metric_info.name,
                description=metric_info.description,
                relevant_columns=metric_info.relevant_columns,
                alias=metric_info.alias,
            )
            for metric_info in retrieved_metrics
        ]

        writer({"type": "progress", "step": "合并召回信息", "status": "success"})
        logger.info(
            f"合并召回信息: 表信息-{[table_info['name'] for table_info in table_infos]},指标信息-{[metric_info['name'] for metric_info in metric_infos]}"
        )

        return {"table_infos": table_infos, "metric_infos": metric_infos}
    except Exception as e:
        writer({"type": "progress", "step": "合并召回信息", "status": "error"})
        logger.error(f"合并召回信息失败: {str(e)}")
        raise

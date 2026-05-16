import yaml
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.llm import llm
from app.agent.state import DataAgentState, TableInfoState
from app.core.log import logger
from app.prompt.prompt_loader import load_prompt


async def filter_table(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    writer = runtime.stream_writer
    writer({"type": "progress", "step": "过滤表格", "status": "running"})

    query = state["query"]
    table_infos: list[TableInfoState] = state["table_infos"]

    try:
        # 用LLM过滤表信息
        prompt = PromptTemplate(template=load_prompt("filter_table_info"), input_variables=["query", "table_infos"])
        output_parser = JsonOutputParser()

        chain = prompt | llm | output_parser

        result = await chain.ainvoke(
            {
                "query": query,
                "table_infos": yaml.dump(
                    table_infos, allow_unicode=True, sort_keys=False
                ),  # 将表信息转换为字符串传递给LLM
            }
        )

        # 利用模型输出过滤table_infos
        # 模型输出示例:
        # {
        #   'fact_order':['order_amount', 'region_id'],
        #   'dim_region':['region_id', 'region_name']
        # }

        """不要边过滤边remove，会导致迭代问题，先过滤出需要的表信息，再统一处理"""
        filtered_table_infos: list[TableInfoState] = []
        for table_info in table_infos:
            if table_info["name"] in result:
                table_info["columns"] = [
                    column for column in table_info["columns"] if column["name"] in result[table_info["name"]]
                ]
                filtered_table_infos.append(table_info)

        writer({"type": "progress", "step": "过滤表格", "status": "success"})
        logger.info(f"过滤后的表信息: {[table_info['name'] for table_info in filtered_table_infos]}")
        return {
            "table_infos": filtered_table_infos
        }  # 注意这里返回的key要和state里一致，后续节点才能正确获取到过滤后的metric_infos

    except Exception as e:
        writer({"type": "progress", "step": "过滤表格", "status": "error"})
        logger.error(f"过滤表失败:{str(e)}")
        raise

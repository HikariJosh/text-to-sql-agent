import yaml
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.llm import llm
from app.agent.state import DataAgentState
from app.core.log import logger
from app.meta.entities.metric_info import MetricInfo
from app.prompt.prompt_loader import load_prompt


async def filter_metric(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """
    过滤指标：用LLM判断哪些指标和用户问题真正相关，去掉不相关的
    召回阶段为了提高召回率会召回较多指标，这里用LLM做精筛，减少SQL生成时的噪声
    """
    writer = runtime.stream_writer
    writer({"type": "progress", "step": "过滤指标", "status": "running"})

    query = state["query"]
    metric_infos: list[MetricInfo] = state["metric_infos"]
    try:
        # 将指标信息序列化为YAML发给LLM，让LLM判断哪些相关
        prompt = PromptTemplate(template=load_prompt("filter_metric_info"), input_variables=["query", "metric_infos"])
        output_parser = JsonOutputParser()

        chain = prompt | llm | output_parser

        result = await chain.ainvoke(
            {"query": query, "metric_infos": yaml.dump(metric_infos, allow_unicode=True, sort_keys=False)}
        )

        # 只保留LLM认为相关的指标
        filtered_metric_infos: list[MetricInfo] = []
        for metric_info in metric_infos:
            if metric_info["name"] in result:
                filtered_metric_infos.append(metric_info)

        writer({"type": "progress", "step": "过滤指标", "status": "success"})
        logger.info(f"过滤后的指标: {[metric_info['name'] for metric_info in filtered_metric_infos]}")

        return {"metric_infos": filtered_metric_infos}

    except Exception as e:
        writer({"type": "progress", "step": "过滤指标", "status": "error"})
        logger.error(f"过滤指标失败:{str(e)}")
        raise

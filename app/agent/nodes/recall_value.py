
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.llm import llm
from app.agent.state import DataAgentState
from app.core.log import logger
from app.meta.entities.value_info import ValueInfo
from app.prompt.prompt_loader import load_prompt


async def recall_value(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """
    召回字段取值：用LLM扩展关键词后，通过ES全文检索匹配维度字段的取值
    例如用户说"华北"，能召回"region"字段的取值"华北地区"
    和recall_column不同，这里不需要embedding，因为ES用的是IK分词做全文匹配
    """
    writer = runtime.stream_writer
    writer({"type": "progress", "step": "召回字段取值", "status": "running"})

    query = state["query"]
    keywords = state["keywords"]

    value_es_repository = runtime.context["value_es_repository"]

    try:
        # 使用LLM扩展关键词，获取更多可能的字段取值
        prompt = PromptTemplate(template=load_prompt("extend_keywords_for_value_recall"), input_variables=["query"])
        output_parser = JsonOutputParser()

        chain = prompt | llm | output_parser

        result = await chain.ainvoke({"query": query})

        # 使用扩展后的关键词在ES中全文检索字段取值
        values_map: dict[str, ValueInfo] = {}
        keywords = list(set(keywords + result))
        logger.info(f"召回字段取值扩展关键词：{keywords}")
        for keyword in keywords:
            values: list[ValueInfo] = await value_es_repository.search(keyword)
            for value in values:
                value_id = value.id
                if value_id not in values_map:
                    values_map[value_id] = value

        retrieved_values = list(values_map.values())

        writer({"type": "progress", "step": "召回字段取值", "status": "success"})
        logger.info(f"召回字段取值：{list(values_map.keys())}")

        # 注意这里返回的key要和state里一致，后续节点才能正确获取到召回的字段取值
        return {"retrieved_values": retrieved_values}
    except Exception as e:
        writer({"type": "progress", "step": "召回字段取值", "status": "error"})
        logger.error(f"召回字段取值失败: {str(e)}")
        raise

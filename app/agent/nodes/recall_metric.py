from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.llm import llm
from app.agent.state import DataAgentState
from app.core.log import logger
from app.meta.entities.metric_info import MetricInfo
from app.prompt.prompt_loader import load_prompt


async def recall_metric(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """
    召回指标信息：用LLM扩展关键词后，通过Qdrant向量检索匹配相关指标
    例如用户说"销售额"，能召回"销售总额"、"毛利额"等相关指标
    流程和recall_column类似：LLM扩展关键词 → embedding向量化 → Qdrant余弦相似度检索
    """
    writer = runtime.stream_writer
    writer({"type": "progress", "step": "召回指标", "status": "running"})

    query = state["query"]
    keywords = state["keywords"]

    embedding_repository = runtime.context["embedding_repository"]
    metric_qdrant_repository = runtime.context["metric_qdrant_repository"]

    try:
        # 使用LLM扩展关键词，获取更多相关指标概念
        prompt = PromptTemplate(template=load_prompt("extend_keywords_for_metric_recall"), input_variables=["query"])
        output_parser = JsonOutputParser()

        chain = prompt | llm | output_parser
        result = await chain.ainvoke({"query": query})
        # 合并原始关键词和扩展关键词，去重
        keywords = list(set(keywords + result))

        logger.info(f"召回指标信息扩展关键词：{keywords}")

        # 使用字典去重，key为metric_id，value为MetricInfo对象
        retrieved_metrics_map: dict[str, MetricInfo] = {}
        for keyword in keywords:
            # 将关键词向量化后在Qdrant中检索相似指标
            embeddings = await embedding_repository.embed([keyword])
            keyword_vector = embeddings[0]
            payloads: list[MetricInfo] = await metric_qdrant_repository.search(keyword_vector)
            for payload in payloads:
                metric_id = payload.id
                if metric_id not in retrieved_metrics_map:
                    retrieved_metrics_map[metric_id] = payload

        retrieved_metrics = list(retrieved_metrics_map.values())

        writer({"type": "progress", "step": "召回指标", "status": "success"})
        logger.info(f"召回指标信息：{list(retrieved_metrics_map.keys())}")
        return {"retrieved_metrics": retrieved_metrics}

    except Exception as e:
        writer({"type": "progress", "step": "召回指标", "status": "error"})
        logger.error(f"召回指标信息失败: {str(e)}")
        raise

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.llm import llm
from app.agent.state import DataAgentState
from app.core.log import logger
from app.meta.entities.column_info import ColumnInfo
from app.prompt.prompt_loader import load_prompt


async def recall_column(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """召回与用户查询相关的数据库字段信息"""
    writer = runtime.stream_writer
    writer({"type": "progress", "step": "召回字段", "status": "running"})

    query = state["query"]
    keywords = state["keywords"]

    embedding_repository = runtime.context["embedding_repository"]
    column_qdrant_repository = runtime.context["column_qdrant_repository"]

    try:
        # 1. 使用LLM扩展关键词，获取更多相关词汇
        prompt = PromptTemplate(
            template=load_prompt("extend_keywords_for_column_recall"),
            input_variables=["query"],
        )
        output_parser = JsonOutputParser()
        chain = prompt | llm | output_parser
        extended_keywords = await chain.ainvoke({"query": query})

        # 2. 合并原始关键词和扩展关键词，去重
        all_keywords = list(set(keywords + extended_keywords))
        logger.info(f"字段召回扩展关键词：{all_keywords}")

        # 3. 对每个关键词进行向量搜索，召回相关字段
        retrieved_columns_map: dict[str, ColumnInfo] = {}
        for keyword in all_keywords:
            # 将关键词转换为向量
            embeddings = await embedding_repository.embed([keyword])
            keyword_vector = embeddings[0]

            # 在向量数据库中搜索相似字段
            recalled_columns: list[ColumnInfo] = await column_qdrant_repository.search(embeded_keyword=keyword_vector)

            # 使用字典去重，避免同一字段被多次召回
            for column in recalled_columns:
                if column.id not in retrieved_columns_map:
                    retrieved_columns_map[column.id] = column

        # 4. 返回去重后的字段列表
        retrieved_columns: list[ColumnInfo] = list(retrieved_columns_map.values())

        # 5. 发送成功状态和日志
        writer({"type": "progress", "step": "召回字段", "status": "success"})
        logger.info(f"成功召回字段：{list(retrieved_columns_map.keys())}")

        return {"retrieved_columns": retrieved_columns}

    except Exception as e:
        writer({"type": "progress", "step": "召回字段", "status": "error"})
        logger.error(f"字段召回失败: {str(e)}")
        raise

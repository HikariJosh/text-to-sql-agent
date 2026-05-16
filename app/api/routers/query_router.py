"""
查询路由模块：定义API接口

接口列表：
  POST /api/query    — 自然语言查询，返回SSE流式响应
  GET  /api/suggestions — 生成提示问题，基于meta库表结构让LLM生成示例查询

SSE（Server-Sent Events）说明：
  /api/query使用StreamingResponse以text/event-stream格式返回数据，
  前端通过fetch+ReadableStream逐条接收事件。
  每个事件格式：data: {"type": "...", ...}\n\n
"""

import random

from fastapi import APIRouter
from fastapi.params import Depends
from langchain.chat_models import init_chat_model
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from starlette.responses import StreamingResponse

from app.api.dependencies import get_meta_mysql_repository, get_query_service
from app.api.schemas.query_schema import QuerySchema
from app.conf.app_config import app_config
from app.prompt.prompt_loader import load_prompt

# 提示问题专用LLM：temperature=1.0增加随机性，让每次生成的问题更多样化
# 主LLM的temperature=0（确定性），这里单独创建一个实例避免影响SQL生成
suggestion_llm = init_chat_model(
    model=app_config.llm.model_name,
    model_provider="openai",
    api_key=app_config.llm.api_key,
    base_url=app_config.llm.base_url,
    temperature=1.0,
)
from app.repositories.mysql.meta_repository import MetaRepository
from app.services.query_service import QueryService

query_router = APIRouter()


@query_router.post("/api/query")
async def query(query: QuerySchema, query_service: QueryService = Depends(get_query_service)):
    """
    查询接口：接收自然语言问题，返回SSE流式响应

    请求体（QuerySchema）：
      - query: str — 用户的自然语言查询，如"2012年3月各渠道的会话数"
      - chat_history: list[dict] — 对话历史，用于多轮对话上下文理解

    依赖注入：
      - Depends(get_query_service) 链式注入所有外部服务的repo和client
      - QueryService内部组装成agent所需的DataAgentContext

    返回：
      StreamingResponse，media_type="text/event-stream"
      事件类型：progress/result/thinking/sql/clarify/summary/error
    """
    return StreamingResponse(query_service.query(query.query, query.chat_history), media_type="text/event-stream")


@query_router.get("/api/suggestions")
async def suggestions(meta_repo: MetaRepository = Depends(get_meta_mysql_repository)):
    """
    提示问题生成接口：扫描meta库的表和字段，让LLM基于实际数据结构生成示例查询

    实现流程：
      1. 通过MetaRepository查询meta库中所有表（table_info表）
      2. 遍历每张表，查询其所有字段（column_info表）
      3. 将表结构格式化为文本："- 表名: 表描述 | 字段: 字段名(描述), ..."
      4. 将表结构文本传给LLM，让LLM生成3个基于实际数据的查询问题
      5. 返回给前端展示为空状态的提示按钮

    依赖注入：
      - Depends(get_meta_mysql_repository) 注入meta库的repository
      - 每次请求创建独立的数据库session，请求结束后自动关闭

    返回：
      {"suggestions": ["问题1", "问题2", "问题3"]}

    降级策略：
      - LLM调用失败时返回硬编码的默认问题，确保前端始终有内容展示

    token消耗：
      只传表名+字段描述（不含字段类型、示例值等），token量很少（约200-500 tokens）
    """
    try:
        # 第1步：查询所有表信息
        tables = await meta_repo.get_all_table_infos()

        # 第2步：遍历每张表，获取字段信息，格式化为一行文本
        schema_lines = []
        for t in tables:
            cols = await meta_repo.get_columns_by_table_id(t.id)
            # 只取字段名和描述，不含类型和示例值，减少token消耗
            col_str = ", ".join(f"{c.name}({c.description or c.type})" for c in cols)
            schema_lines.append(f"- {t.name}: {t.description} | 字段: {col_str}")
        schema_text = "\n".join(schema_lines)

        # 第3步：调用LLM生成提示问题
        # 使用suggestion_llm（temperature=1.0），让每次生成的问题更多样化
        prompt = PromptTemplate(
            template=load_prompt("suggestions"),
            input_variables=["schema"],
        )
        chain = prompt | suggestion_llm | StrOutputParser()
        result = await chain.ainvoke({"schema": schema_text})

        # 第4步：按行分割，随机抽取3个（5个简单+5个有深度，每次随机组合）
        questions = [q.strip() for q in result.strip().split("\n") if q.strip()]
        if len(questions) > 3:
            questions = random.sample(questions, 3)
        return {"suggestions": questions}

    except Exception:
        # LLM失败时不显示提示问题
        return {"suggestions": []}

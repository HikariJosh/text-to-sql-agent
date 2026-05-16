from pydantic import BaseModel, Field


class QuerySchema(BaseModel):
    """查询请求体校验模型，FastAPI会自动校验请求体是否符合这个结构"""

    query: str = Field(..., min_length=1, max_length=2000, description="用户输入的自然语言问题")
    chat_history: list[dict] = Field(default_factory=list, description="对话历史")

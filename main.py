import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers.health_router import health_router
from app.api.routers.query_router import query_router
from app.core.context import request_id_ctx_var
from app.core.lifespan import decrement_active_requests, increment_active_requests, lifespan

# 创建FastAPI应用，注册lifespan管理外部服务连接的生命周期
app = FastAPI(lifespan=lifespan)

# CORS 中间件，支持前端跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(health_router)
app.include_router(query_router)


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """
    HTTP中间件：给每个请求生成唯一的request_id
    这个request_id会通过ContextVar贯穿整个请求的处理过程，
    包括agent节点的日志输出，方便排查问题时追踪一个请求的完整链路
    """
    request_id_ctx_var.set(uuid.uuid4())  # 请求进入时生成ID
    increment_active_requests()
    try:
        response = await call_next(request)  # 处理请求
    finally:
        decrement_active_requests()
    return response


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)

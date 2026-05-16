"""
日志配置：使用loguru作为日志框架，支持自动注入request_id
每条日志都会带上当前请求的request_id，方便在并发场景下追踪一个请求的完整链路
"""

import asyncio
import sys
from pathlib import Path

from loguru import logger

from app.conf.app_config import app_config
from app.core.context import request_id_ctx_var

# 日志格式：时间 | 级别 | request_id | 文件名:函数:行号 - 消息
log_format = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<magenta>request_id - {extra[request_id]}</magenta> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
    "<level>{message}</level>"
)


def inject_request_id(record):
    """给每条日志注入当前请求的request_id"""
    request_id = request_id_ctx_var.get()
    record["extra"]["request_id"] = request_id


logger.remove()
# 给日志打补丁，使其支持注入request_id
logger = logger.patch(inject_request_id)
# 根据配置决定是否输出到控制台
if app_config.logging.console.enable:
    logger.add(sink=sys.stdout, level=app_config.logging.console.level, format=log_format)
# 根据配置决定是否输出到文件
if app_config.logging.file.enable:
    path = Path(app_config.logging.file.path)
    path.mkdir(parents=True, exist_ok=True)
    logger.add(
        sink=path / "app.log",
        level=app_config.logging.file.level,
        format=log_format,
        rotation=app_config.logging.file.rotation,  # 日志轮转策略，如"10 MB"
        retention=app_config.logging.file.retention,  # 日志保留时间，如"7 days"
        encoding="utf-8",
    )

if __name__ == "__main__":

    async def graph(request: str):
        # 打印日志
        logger.info(request)

    async def test1():
        # 接收到请求
        request_id_ctx_var.set("request-1")

        # 模拟处理
        await asyncio.sleep(1)
        await graph("request-1")

    async def test2():
        # 接收到请求
        request_id_ctx_var.set("request-2")

        # 模拟处理
        await asyncio.sleep(1)
        await graph("request-2")

    async def main():
        await asyncio.gather(test1(), test2())

    asyncio.run(main())

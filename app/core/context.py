from contextvars import ContextVar

# 请求级别的上下文变量，用于存储每个请求的唯一ID
# ContextVar是Python的异步上下文变量，保证在同一个请求的整个生命周期内都能拿到同一个值
# 即使在多个async函数之间传递也不丢失，比传参更优雅
# 默认值"1"用于非请求场景(如离线脚本)的日志输出
request_id_ctx_var = ContextVar("request_id", default="1")

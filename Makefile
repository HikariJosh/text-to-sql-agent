.PHONY: help dev install test lint format \
       up down rebuild rebuild-no-cache \
       build health \
       logs logs-app logs-embedding

help: ## 显示所有可用命令
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ============================================================
#  开发
# ============================================================

dev: ## 启动本地开发服务器 (localhost:8000)
	uvicorn main:app --reload --host 0.0.0.0 --port 8000

install: ## 安装/更新依赖
	uv sync

# ============================================================
#  Docker 容器管理
# ============================================================

up: ## 启动所有容器 (MySQL, Qdrant, ES, TEI, App, Frontend, Kibana)
	cd docker && docker compose up -d

down: ## 停止所有容器
	cd docker && docker compose down

rebuild: ## 重建 App 镜像并重启（代码变更后使用）
	cd docker && docker compose up -d --build app

rebuild-no-cache: ## 清除缓存重建所有镜像（依赖变更后使用）
	cd docker && docker compose build --no-cache && docker compose up -d

# ============================================================
#  知识库
# ============================================================

build: ## 构建元数据知识库（写入 MySQL + Qdrant + ES）
	uv run python -m app.scripts.build_meta_knowledge \
		-c conf/meta_config/table_column_info.yaml \
		-c conf/meta_config/metric_info.yaml

# ============================================================
#  检查 & 测试
# ============================================================

health: ## 检查所有服务健康状态
	@curl -s http://localhost:8000/health | python -m json.tool

test: ## 运行单元测试
	uv run pytest -v

lint: ## 代码检查
	uv run ruff check .

format: ## 代码格式化
	uv run ruff format .
	uv run ruff check --fix .

# ============================================================
#  日志
# ============================================================

logs: ## 查看所有容器最近 50 行日志
	cd docker && docker compose logs --tail 50

logs-app: ## 查看 App 容器日志
	cd docker && docker compose logs app --tail 50

logs-embedding: ## 查看 TEI Embedding 容器日志
	cd docker && docker compose logs embedding --tail 50

# Data Agent

Text-to-SQL Agent：用户用自然语言提问，系统自动生成 SQL 查询数据仓库并返回结果。

```
用户提问 → 关键词提取 → 多路召回(列/值/指标) → 合并 → 过滤 → 思考分析 → 生成SQL → 校验 → 执行 → 总结
```

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | FastAPI + LangGraph |
| LLM | OpenAI 兼容 API（可替换） |
| 向量数据库 | Qdrant |
| 搜索引擎 | Elasticsearch |
| Embedding | BGE-large-zh-v1.5 |
| 数据库 | MySQL 8.0 |
| 前端 | Vue 3 (Composition API) |
| 部署 | Docker Compose |

## 核心功能

- **自然语言查询**：输入中文问题，自动生成 SQL 并执行
- **流式响应**：SSE 实时返回处理进度、思考过程、SQL、查询结果
- **思考过程**：LLM 流式输出分析推理过程，可折叠查看
- **结果总结**：自动用自然语言总结查询结果的关键发现
- **智能提示**：基于实际数据库表结构，LLM 动态生成示例问题
- **多轮对话**：支持上下文理解，可追问和补充
- **13 步处理流水线**：关键词提取 → 字段召回 → 值召回 → 指标召回 → 合并 → 过滤表格 → 过滤指标 → 补充上下文 → 思考分析 → 生成SQL → 验证SQL → 执行SQL → 生成总结

## 快速启动

```bash
# 1. 安装依赖
make install

# 2. 配置密钥
cp .env.example .env   # 编辑填入密码和 API Key

# 3. 下载 embedding 模型（~1.2GB，仅首次需要）
bash scripts/setup_embedding.sh

# 4. 启动基础设施
make up

# 5. 构建知识库
make build

# 6. 启动服务
make dev
```

访问 `http://localhost:3000` 使用前端界面，或 `http://localhost:8000/docs` 查看 API 文档。

## 配置文件说明

| 文件 | 职责 | 谁来改 |
|------|------|--------|
| `.env` | 密码、API Key（gitignore） | 运维 |
| `conf/app_config.yaml` | DB/Qdrant/ES/LLM 连接配置 | 开发 |
| `docker/docker-compose.yaml` | 基础设施服务定义 | 运维 |
| `docker/mysql/init_meta.sql` | 元数据库建表（系统自用） | — |
| `docker/mysql/init_dw.sql` | 数仓建表 + 样本数据 | 开发 |
| `prompts/*.prompt` | LLM Prompt 模板 | 开发 |

## 切换业务领域

```bash
# 1. 将新业务数据导入 dw 库
# 2. 自动扫描生成业务配置
make scan
# 3. 编辑 conf/business.yaml，补充 description 和 alias
# 4. 构建知识库
make build
```

## Makefile 命令

| 命令 | 说明 |
|------|------|
| `make dev` | 启动开发服务器（热重载） |
| `make test` | 运行测试 |
| `make lint` | 代码检查 |
| `make format` | 代码格式化 |
| `make up` | 启动基础设施 |
| `make down` | 停止基础设施 |
| `make scan` | 扫描 dw 库生成 business.yaml |
| `make build` | 构建知识库 |

## 项目结构

```
app/
├── agent/          # LangGraph Agent（13 个节点）
│   ├── nodes/      # 各处理节点实现
│   ├── state.py    # 状态定义
│   └── graph.py    # 图编排
├── api/            # 路由、校验、依赖注入
│   ├── routers/    # API 端点
│   ├── schemas/    # 请求/响应模型
│   └── dependencies.py  # 依赖注入
├── services/       # 业务编排
├── clients/        # 外部服务客户端（MySQL/Qdrant/ES/Embedding）
├── repositories/   # 数据访问层
├── meta/           # 元数据实体和 ORM
├── conf/           # 配置加载
├── core/           # 生命周期、日志
├── scripts/        # CLI 工具
└── prompt/         # Prompt 模板加载器
prompts/            # LLM Prompt 模板（.prompt 文件）
conf/               # 配置文件
docker/             # 基础设施
├── app/            # 应用 Dockerfile
├── frontend/       # 前端 Dockerfile
├── elasticsearch/  # ES 配置和插件
├── embedding/      # Embedding 模型（需单独下载）
└── mysql/          # SQL 初始化脚本
fronted/            # Vue 3 前端
tests/              # 测试
scripts/            # 辅助脚本
```

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/query` | 自然语言查询，返回 SSE 流式响应 |
| GET | `/api/suggestions` | 获取基于数据库结构的示例问题 |

### SSE 事件类型

| type | 说明 |
|------|------|
| `progress` | 处理步骤状态更新（pending/running/success/error） |
| `thinking` | LLM 思考过程（支持流式逐字输出） |
| `sql` | 生成的 SQL 语句 |
| `result` | 查询结果数据 |
| `summary` | 自然语言总结 |
| `clarify` | 澄清问题 |
| `error` | 错误信息 |

## License

MIT

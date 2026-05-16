# Text-to-SQL Agent

> 用自然语言查询你的数据仓库，AI 自动生成 SQL 并返回分析结果。

基于 LangGraph 构建的智能数据查询代理，支持中文自然语言输入、多轮对话、流式思考过程展示，以及自动结果总结。

## 工作流程

```
┌─────────────┐
│  用户提问    │  "上个月各渠道的转化率是多少？"
└──────┬──────┘
       ▼
┌─────────────┐
│ 关键词提取   │  渠道、转化率、上个月
└──────┬──────┘
       ▼
┌─────────────────────────────────────┐
│          多路并行召回                │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐
│  │ 字段召回  │ │ 值召回   │ │ 指标召回  │
│  └──────────┘ └──────────┘ └──────────┘
└──────────────┬──────────────────────┘
               ▼
┌─────────────┐    ┌─────────────┐
│ 合并 & 过滤 │───▶│  思考分析    │  LLM 推理如何构建 SQL
└──────┬──────┘    └──────┬──────┘
       ▼                  ▼
┌─────────────┐    ┌─────────────┐
│  生成 SQL   │───▶│  验证 SQL    │  语法检查 + 自动修正
└──────┬──────┘    └──────┬──────┘
       ▼                  ▼
┌─────────────┐    ┌─────────────┐
│  执行 SQL   │───▶│  生成总结    │  自然语言概括关键发现
└─────────────┘    └─────────────┘
```

## 核心特性

**智能查询**
- 中文自然语言输入，自动生成 MySQL 语法的 SQL
- 多路召回（字段、字段值、业务指标），确保 SQL 准确
- 支持多轮对话，可追问和补充条件

**实时反馈**
- SSE 流式返回 13 步处理进度，每步实时状态更新
- LLM 思考过程逐字流式输出，可折叠查看
- 生成的 SQL 可一键复制

**智能分析**
- 查询结果自动生成中文摘要，突出关键数据和趋势
- 首页根据实际数据库表结构动态生成提示问题
- 每次刷新随机展示不同问题组合

## 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| Agent 框架 | LangGraph | 13 节点有向图，支持条件分支和并行执行 |
| 后端 | FastAPI | 异步 API，SSE 流式响应 |
| LLM | OpenAI 兼容 API | 可替换为任意兼容接口 |
| 向量检索 | Qdrant | 字段和指标的语义召回 |
| 全文检索 | Elasticsearch | 字段值的模糊匹配 |
| Embedding | BGE-large-zh-v1.5 | 中文语义向量模型 |
| 数据库 | MySQL 8.0 | 元数据库 + 数据仓库 |
| 前端 | Vue 3 | Composition API，极简风格 |
| 部署 | Docker Compose | 一键启动全部基础设施 |

## 快速启动

### 1. 克隆仓库

```bash
git clone https://github.com/HikariJosh/text-to-sql-agent.git
cd text-to-sql-agent
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入你的数据库密码和 LLM API Key
```

### 3. 下载 Embedding 模型

```bash
# 模型约 1.2GB，仅首次需要下载
bash scripts/setup_embedding.sh
```

### 4. 启动服务

```bash
# 安装 Python 依赖
make install

# 启动所有基础设施（MySQL、Qdrant、ES、Embedding）
make up

# 构建知识库（扫描表结构、写入向量库）
make build

# 启动应用
make dev
```

### 5. 访问

- **前端界面**：http://localhost:3000
- **API 文档**：http://localhost:8000/docs

## 项目结构

```
text-to-sql-agent/
├── app/
│   ├── agent/                # LangGraph Agent
│   │   ├── nodes/            # 13 个处理节点
│   │   │   ├── extract_keywords.py    # 关键词提取
│   │   │   ├── recall_column.py       # 字段召回
│   │   │   ├── recall_value.py        # 值召回
│   │   │   ├── recall_metric.py       # 指标召回
│   │   │   ├── merge_retrieved_info.py # 合并召回结果
│   │   │   ├── filter_table.py        # 过滤表格
│   │   │   ├── filter_metric.py       # 过滤指标
│   │   │   ├── add_extra_context.py   # 补充上下文
│   │   │   ├── think.py               # 思考分析（流式输出）
│   │   │   ├── generate_sql.py        # 生成 SQL
│   │   │   ├── validate_sql.py        # 验证 & 修正 SQL
│   │   │   ├── execute_sql.py         # 执行 SQL
│   │   │   └── summarize.py           # 生成总结
│   │   ├── state.py          # 状态定义
│   │   └── graph.py          # 图编排
│   ├── api/                  # API 层
│   │   ├── routers/          # 路由（query、suggestions）
│   │   ├── schemas/          # 请求模型
│   │   └── dependencies.py   # 依赖注入
│   ├── services/             # 业务编排
│   ├── clients/              # 外部服务客户端
│   ├── repositories/         # 数据访问层（MySQL、Qdrant、ES）
│   ├── meta/                 # 元数据实体 & ORM
│   ├── conf/                 # 配置加载
│   ├── core/                 # 生命周期、日志
│   └── prompt/               # Prompt 模板加载器
├── prompts/                  # LLM Prompt 模板
├── conf/                     # 配置文件
├── docker/                   # Docker 配置
│   ├── app/                  # 应用 Dockerfile
│   ├── frontend/             # 前端 Dockerfile
│   ├── elasticsearch/        # ES + IK 分词插件
│   ├── embedding/            # Embedding 模型（需下载）
│   └── mysql/                # 数据库初始化 SQL
├── fronted/                  # Vue 3 前端
├── tests/                    # 测试
└── scripts/                  # 辅助脚本
```

## API

### `POST /api/query`

自然语言查询，返回 SSE 流式响应。

**请求体**：
```json
{
  "query": "上个月各渠道的会话数",
  "chat_history": []
}
```

**SSE 事件类型**：

| type | 说明 | 数据示例 |
|------|------|----------|
| `progress` | 处理步骤状态 | `{"step": "生成SQL", "status": "success"}` |
| `thinking` | LLM 思考过程 | `{"content": "用户想查...", "stream": true}` |
| `sql` | 生成的 SQL | `{"sql": "SELECT ..."}` |
| `result` | 查询结果 | `{"data": [...]}` |
| `summary` | 结果总结 | `{"content": "本月各渠道..."}` |
| `clarify` | 澄清问题 | `{"message": "请问是..."}` |
| `error` | 错误信息 | `{"message": "SQL 执行失败"}` |

### `GET /api/suggestions`

获取基于数据库实际表结构的示例问题，每次随机返回 3 个。

**响应**：
```json
{
  "suggestions": ["各渠道会话数有多少", "销量top10的产品是哪些", "退款率最高的产品是哪个"]
}
```

## 切换业务场景

本项目默认附带电商数据仓库样本（Maven Fuzzy Factory）。切换到你自己的业务数据：

1. 将数据导入 MySQL 的 `dw` 库
2. 运行 `make scan` 自动扫描表结构
3. 编辑 `conf/meta_config/` 下的 YAML，补充业务描述
4. 运行 `make build` 重建知识库

## 配置说明

| 文件 | 说明 |
|------|------|
| `.env` | 敏感信息（密码、API Key），不会提交到 Git |
| `conf/app_config.yaml` | 服务连接配置（数据库、向量库、LLM） |
| `conf/meta_config/` | 业务元数据（表、字段、指标定义） |
| `prompts/*.prompt` | LLM Prompt 模板，可按需调整 |

## Makefile

| 命令 | 说明 |
|------|------|
| `make install` | 安装 Python 依赖 |
| `make dev` | 启动开发服务器（热重载） |
| `make up` | 启动 Docker 基础设施 |
| `make down` | 停止 Docker 基础设施 |
| `make build` | 构建向量知识库 |
| `make scan` | 扫描数据库生成元数据配置 |
| `make test` | 运行测试 |
| `make lint` | 代码检查 |
| `make format` | 代码格式化 |

## License

[MIT](LICENSE)

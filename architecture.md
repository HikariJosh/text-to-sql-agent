# data-agent 项目架构文档

## 概述

这是一个 **Text-to-SQL Agent**，基于 FastAPI + LangGraph 构建。用户输入自然语言问题，系统从多个存储中检索相关表结构知识，使用 LLM 生成 SQL，校验/修正后执行，并通过 SSE 流式返回结果。

---

## 整体链路

```
用户提问 "统计华北地区的销售总额"
        │
        ▼
┌─────────────────────────────────────────────────────┐
│  main.py  (FastAPI 入口, 端口 8000)                  │
│  ├── middleware: 给每个请求生成 request_id            │
│  └── lifespan: 启动时 init 所有 client, 关闭时 close  │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│  query_router.py  POST /api/query                    │
│  └── dependencies.py (DI) 组装所有依赖注入 QueryService│
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│  query_service.py  编排者                            │
│  创建 Context(所有repo+client) → 调用 graph.astream   │
│  每个 chunk 包装成 SSE (data: {...}\n\n) 返回前端       │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌═══════════════════════════════════════════════════════┐
║  agent/graph.py  LangGraph 状态图 (核心流程)           ║
║                                                       ║
║  START                                                ║
║    │                                                  ║
║    ▼                                                  ║
║  ① extract_keywords  (jieba 分词抽取关键词)             ║
║    │                                                  ║
║    ├──────────────┬──────────────┐                    ║
║    ▼              ▼              ▼                    ║
║  ②a             ②b             ②c                    ║
║  recall_column  recall_value  recall_metric           ║
║  (Qdrant向量)   (ES全文检索)   (Qdrant向量)            ║
║  embedding↑      ↓             embedding↑             ║
║    │              │              │                    ║
║    └──────────────┴──────────────┘                    ║
║                    │                                  ║
║                    ▼                                  ║
║  ③ merge_retrieved_info  (合并3路召回结果)              ║
║    │                                                  ║
║    ├──────────────┬──────────────┐                    ║
║    ▼              ▼              ▼                    ║
║  ④a             ④b             ⑤                     ║
║  filter_table  filter_metric  add_extra_context       ║
║  (LLM裁剪表)   (LLM裁剪指标)  (加日期+DB版本)          ║
║    │              │              │                    ║
║    └──────────────┴──────────────┘                    ║
║                    │                                  ║
║                    ▼                                  ║
║  ⑥ generate_sql  (LLM 生成 SQL)                      ║
║    │                                                  ║
║    ▼                                                  ║
║  ⑦ validate_sql  (EXPLAIN 验证语法)                   ║
║    │              \                                   ║
║    │  成功         \ 失败                              ║
║    ▼               ▼                                  ║
║  ⑨ execute_sql   ⑧ correct_sql (LLM修正SQL)          ║
║    │               │                                  ║
║    │               ▼                                  ║
║    │             ⑨ execute_sql                        ║
║    │               │                                  ║
║    ▼               ▼                                  ║
║   END            END                                  ║
╚═══════════════════════════════════════════════════════╝
```

---

## 各层职责

| 层 | 文件夹 | 做什么 |
|---|---|---|
| **入口层** | `main.py` | FastAPI 应用, 中间件, 生命周期管理 |
| **API层** | `app/api/` | 路由定义、请求校验(Pydantic)、依赖注入 |
| **服务层** | `app/services/` | `QueryService` 编排 agent 图, `MetaKnowledgeService` 离线构建知识库 |
| **Agent层** | `app/agent/` | LangGraph 状态图 + 12 个节点, 是整个系统的大脑 |
| **客户端层** | `app/clients/` | 管理外部服务连接(MySQL/ES/Qdrant/Embedding) |
| **仓库层** | `app/repositories/` | 封装对每个存储的 CRUD 操作 |
| **模型层** | `app/models/` | SQLAlchemy ORM 映射(meta MySQL 的表) |
| **实体层** | `app/entities/` | 纯 dataclass, 业务逻辑用的数据结构 |
| **配置层** | `app/conf/` + `conf/` | YAML 配置加载和校验 |
| **提示词层** | `prompts/` | LLM 的 prompt 模板文件 |

---

## 目录结构

```
data-agent/
├── main.py                                  # FastAPI 入口
├── conf/
│   ├── app_config.yaml                      # 运行时配置 (DB, Qdrant, ES, LLM, 日志)
│   └── meta_config.yaml                     # 知识库 schema 定义 (表, 指标)
├── prompts/
│   ├── extend_keywords_for_column_recall.prompt
│   ├── extend_keywords_for_value_recall.prompt
│   ├── extend_keywords_for_metric_recall.prompt
│   ├── filter_table_info.prompt
│   ├── filter_metric_info.prompt
│   ├── generate_sql.prompt
│   └── correct_sql.prompt
├── app/
│   ├── api/
│   │   ├── routers/query_router.py          # POST /api/query
│   │   ├── schemas/query_schema.py          # Pydantic 请求模型
│   │   └── dependencies.py                  # FastAPI 依赖注入
│   ├── services/
│   │   ├── query_service.py                 # 编排 agent 图执行
│   │   └── meta_knowledge_service.py        # 离线: 从 YAML 构建知识库
│   ├── agent/
│   │   ├── graph.py                         # LangGraph 状态图定义
│   │   ├── state.py                         # DataAgentState 状态类型
│   │   ├── context.py                       # DataAgentContext 上下文类型
│   │   ├── llm.py                           # LLM 单例
│   │   └── nodes/                           # 12 个 agent 节点
│   ├── clients/
│   │   ├── embedding_client_manager.py      # BGE-large-zh 向量化客户端
│   │   ├── es_client_manager.py             # Elasticsearch 异步客户端
│   │   ├── mysql_client_manager.py          # SQLAlchemy 异步引擎 (meta + dw)
│   │   └── qdrant_client_manager.py         # Qdrant 向量数据库客户端
│   ├── repositories/
│   │   ├── qdrant/
│   │   │   ├── column_qdrant_repository.py  # 字段向量检索
│   │   │   └── metric_qdrant_repository.py  # 指标向量检索
│   │   ├── es/
│   │   │   └── value_es_repository.py       # 取值全文检索
│   │   └── mysql/
│   │       ├── meta/                        # 元数据 CRUD
│   │       └── dw/                          # 数仓查询/验证/执行
│   ├── models/                              # SQLAlchemy ORM 模型
│   ├── entities/                            # 纯 dataclass 实体
│   ├── conf/                                # 配置加载逻辑
│   ├── core/                                # 上下文变量, 生命周期, 日志
│   ├── prompt/                              # prompt 加载器
│   └── scripts/                             # 离线脚本 (构建知识库)
└── docker/
    ├── docker-compose.yaml
    ├── elasticsearch/
    ├── embedding/bge-large-zh-v1.5/         # 本地 embedding 模型权重
    └── mysql/
        ├── meta.sql                         # 元数据库初始化
        └── dw.sql                           # 数仓初始化
```

---

## 5 个外部存储

| 存储 | 用途 | Client Manager | Repository |
|---|---|---|---|
| **MySQL (meta)** | 存表/列/指标的元数据 | `meta_mysql_client_manager` | `MetaMySQLRepository` |
| **MySQL (dw)** | 数据仓库, 最终执行 SQL 的地方 | `dw_mysql_client_manager` | `DWMySQLRepository` |
| **Qdrant** | 向量数据库, 语义检索列和指标 | `qdrant_client_manager` | `ColumnQdrantRepository`, `MetricQdrantRepository` |
| **Elasticsearch** | 全文检索维度字段取值 (IK 分词) | `es_client_manager` | `ValueESRepository` |
| **Embedding** | BGE-large-zh-v1.5, 文字转向量 | `embedding_client_manager` | 节点直接调用 |

```
用户问题
   │
   ├─ embedding (BGE向量化) ──→ Qdrant (语义检索列/指标)
   ├─ LLM (关键词扩展)     ──→ ES    (全文检索字段取值)
   ├─ meta MySQL            ──→ 存表/列/指标的元数据
   └─ dw MySQL              ──→ 真正的数据仓库, 最终执行 SQL
```

---

## Agent 节点详解

### ① extract_keywords (抽取关键词)
- 使用 `jieba.analyse.extract_tags()` 分词
- 保留名词、动词、形容词等有意义的词性
- 将原始 query 也加入关键词列表, 去重

### ②a recall_column (召回字段)
- LLM 扩展关键词为字段名
- 对每个关键词: embedding 向量化 → Qdrant 余弦相似度检索 (阈值 0.6)
- 按字段 ID 去重

### ②b recall_value (召回取值)
- LLM 扩展关键词为可能的字段值
- 对每个关键词: ES 全文检索 (IK 分词, 阈值 0.6)
- 按取值 ID 去重

### ②c recall_metric (召回指标)
- LLM 扩展关键词为指标概念
- 对每个关键词: embedding 向量化 → Qdrant 余弦相似度检索
- 按指标 ID 去重

### ③ merge_retrieved_info (合并召回信息)
- 合并 3 路字段来源: 直接召回的列、指标关联的列、取值关联的列
- 将召回的取值作为 `examples` 附加到对应列上
- 强制补充主键/外键列 (确保可以 JOIN)
- 按 table_id 分组, 查询 meta MySQL 获取表元数据
- 构建 `table_infos` 和 `metric_infos`

### ④a filter_table (裁剪表)
- 将 table_infos 序列化为 YAML 发给 LLM
- LLM 返回 JSON: `{表名: [需要的列名]}`
- 裁剪掉 LLM 认为不相关的表和列

### ④b filter_metric (裁剪指标)
- 将 metric_infos 序列化为 YAML 发给 LLM
- LLM 返回 JSON: `[需要的指标名]`
- 裁剪掉 LLM 认为不相关的指标

### ⑤ add_extra_context (补充上下文)
- 计算当前日期、星期、季度
- 查询 dw MySQL 获取数据库版本和方言

### ⑥ generate_sql (生成 SQL)
- 将 table_infos, metric_infos, date_info, db_info 序列化为 YAML
- 发给 LLM 生成 SQL

### ⑦ validate_sql (验证 SQL)
- 在 dw MySQL 上执行 `EXPLAIN {sql}`
- 成功: error = None
- 失败: error = 异常信息

### ⑧ correct_sql (修正 SQL, 仅在验证失败时执行)
- 将原始上下文 + 错误的 SQL + 错误信息发给 LLM
- LLM 返回修正后的 SQL
- 只做一次修正, 不循环

### ⑨ execute_sql (执行 SQL)
- 在 dw MySQL 上执行最终 SQL
- 返回 `list[dict]` 格式的结果
- 通过 stream_writer 发送 `{"type": "result", "data": [...]}`

---

## Agent 状态 (DataAgentState)

| 字段 | 写入节点 | 类型 |
|---|---|---|
| `query` | (初始输入) | `str` |
| `keywords` | `extract_keywords` | `list[str]` |
| `retrieved_columns` | `recall_column` | `list[ColumnInfo]` |
| `retrieved_values` | `recall_value` | `list[ValueInfo]` |
| `retrieved_metrics` | `recall_metric` | `list[MetricInfo]` |
| `table_infos` | `merge_retrieved_info` → `filter_table` 覆写 | `list[TableInfoState]` |
| `metric_infos` | `merge_retrieved_info` → `filter_metric` 覆写 | `list[MetricInfoState]` |
| `date_info` | `add_extra_context` | `DateInfoState` |
| `db_info` | `add_extra_context` | `DBInfoState` |
| `sql` | `generate_sql` → 可能被 `correct_sql` 覆写 | `str` |
| `error` | `validate_sql` | `str` 或 `None` |

---

## SSE 响应格式

前端收到的 SSE 事件流:

```
data: {"type": "progress", "step": "抽取关键字", "status": "running"}
data: {"type": "progress", "step": "抽取关键字", "status": "success"}
data: {"type": "progress", "step": "召回字段", "status": "running"}
data: {"type": "progress", "step": "召回指标", "status": "running"}
data: {"type": "progress", "step": "召回字段取值", "status": "running"}
...
data: {"type": "progress", "step": "生成SQL", "status": "success"}
data: {"type": "progress", "step": "验证SQL", "status": "success"}
data: {"type": "progress", "step": "执行SQL", "status": "running"}
data: {"type": "result", "data": [{"region": "华北", "sales": 10000}, ...]}
data: {"type": "progress", "step": "执行SQL", "status": "success"}
```

---

## 关键设计模式

- **SSE 流式传输**: `graph.astream(stream_mode="custom")` 让每个节点通过 `runtime.stream_writer` 发送任意 JSON, 转为 SSE 推送给前端
- **依赖注入**: FastAPI `Depends()` 链在 `dependencies.py` 中组装, 每个请求创建 DB session, 向量/搜索客户端为单例
- **LLM 裁剪**: `filter_table` 和 `filter_metric` 用 LLM 判断哪些召回的 schema 元素真正相关, 减少噪声
- **验证-修正循环**: SQL 生成后用 EXPLAIN 验证语法, 失败则 LLM 修正一次
- **多存储 RAG**: 同时从 Qdrant(列) + Qdrant(指标) + ES(取值) 三路召回, 合并后再过滤

---

## 离线知识库构建

独立脚本, 在应用运行前执行一次:

```bash
python -m app.scripts.build_meta_knowledge -c conf/meta_config.yaml
```

流程:
1. 解析 `meta_config.yaml` 中的表和指标定义
2. 对每张表: 查询 dw 获取列类型和示例值 → 存入 meta MySQL → embedding 向量化后存入 Qdrant
3. 对 `sync: true` 的列: 从 dw 拉取所有去重值 → 存入 ES (IK 分词)
4. 对每个指标: 存入 meta MySQL → embedding 向量化后存入 Qdrant

---

## 运行依赖

| 服务 | 端口 | 用途 |
|---|---|---|
| MySQL | 3306 | meta 库 + dw 库 |
| Qdrant | 6333 | 向量数据库 |
| Elasticsearch | 9200 | 全文检索 |
| Kibana | 5601 | ES 可视化 (可选) |
| Embedding (TEI) | 8081 | BGE-large-zh 推理服务 |
| FastAPI | 8000 | 应用服务 |

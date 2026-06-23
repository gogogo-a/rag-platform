# AI 交接文档：Qdrant 向量库改造

## 接手摘要

这个项目已经从 Milvus 全面切到 Qdrant。后续 AI 或开发者接手时，不要再恢复 Milvus，也不要再引入 `pymilvus`、`langchain-milvus` 之类依赖。

接手时按以下结论执行：

- 向量库统一使用 Qdrant。
- 文档上传、检索、删除、chunk 统计都走 Qdrant。
- QA 相似问答缓存也走 Qdrant。
- MCP 知识库搜索工具只调用 Qdrant。
- MCP 自定义工具默认全部启用，不再受 `ENABLE_EXTRA_MCP_TOOLS` 限制。
- 后续字段统一使用 `vector_id`，旧的 `milvus_id` 只作为兼容读取，不应继续新增。
- 启动时只需要 MongoDB、Redis、Qdrant、MCP 等服务，不再需要 Milvus。
- 旧 Milvus 数据不做自动迁移，如果需要旧数据，应走单独快照导入 Qdrant。
- 页面和接口文案不要出现 Milvus，统一写“向量库”或 “Qdrant”。
- 不要恢复 Milvus 文件、Docker 配置或工具限制开关。

## 当前目标

本项目已从 Milvus 向量库切换为 Qdrant。后续接手时，默认不要再恢复 Milvus，也不要再引入 `pymilvus` 或 `langchain-milvus`。

当前向量相关目标：

- 文档向量写入、检索、删除、计数全部走 Qdrant。
- QA 缓存的向量写入、相似问题检索和删除全部走 Qdrant。
- MCP 自定义工具默认全部启用。
- 用户可见页面和接口文案不出现 Milvus。

## 关键文件

- `internal/db/qdrant.py`
  - Qdrant 统一客户端封装。
  - 提供 collection 初始化、文档向量 upsert、QA 缓存 upsert、检索、按文档删除、计数、scroll 等方法。

- `main.py`
  - 启动时会初始化 Qdrant 文档集合和 QA 缓存集合。
  - 启动流程不再连接 Milvus。

- `internal/document_client/document_processor.py`
  - 文档解析后生成 embedding，并写入 Qdrant。
  - 删除任务按 `document_uuid` 删除 Qdrant 向量。

- `internal/service/orm/document_sever.py`
  - 文档详情和列表的 `chunk_count` 从 Qdrant 查询，失败时回退 MongoDB `chunks`。
  - 删除文档时同步删除 Qdrant 向量。

- `pkg/agent_tools_mcp/knowledge_search_mcp.py`
  - MCP 知识库检索直接调用 Qdrant。
  - 普通用户仍过滤 `permission=1` 的文档。

- `internal/service/ai/thought_chain_store.py`
  - QA 缓存写入 Qdrant。
  - 使用 `vector_id` 记录向量 ID。

- `internal/service/ai/similar_qa_cache.py`
  - 相似问答检索和缓存删除走 Qdrant。

- `internal/service/orm/qa_cache_service.py`
  - QA 缓存管理以 MongoDB 的 `ThoughtChainModel` 为主，Qdrant 只负责向量检索和删除。

- `internal/service/visualization/document_3d_service.py`
  - 3D 可视化从 Qdrant scroll 读取向量。

- `pkg/agent_tools_mcp/mcp_config.py`
  - MCP 工具默认全部加载，不再使用 `ENABLE_EXTRA_MCP_TOOLS`。

## 配置项

`.env` / `env_template.txt` 中向量库配置为：

```env
QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_COLLECTION_NAME=documents
QDRANT_QA_COLLECTION_NAME=qa_cache
VECTOR_DIMENSION=1024
```

依赖中应保留：

```txt
qdrant-client
```

依赖中不应出现：

```txt
pymilvus
langchain-milvus
```

## 数据流

文档上传：

1. API 保存文件和 MongoDB 文档记录。
2. `document_processor` 解析文本并分块。
3. `embedding_service` 生成向量。
4. `qdrant_client.upsert_documents()` 写入 Qdrant。
5. 文档状态更新为处理完成。

知识库检索：

1. MCP 工具收到 query。
2. `embedding_service.encode_query()` 生成 query embedding。
3. `qdrant_client.search_documents()` 检索 Qdrant。
4. 根据 `permission` 过滤结果。
5. 返回 context 和引用文档列表。

QA 缓存：

1. 思维链写入 MongoDB。
2. 需要缓存时，问题 embedding 写入 `QDRANT_QA_COLLECTION_NAME`。
3. 相似问题检索从 QA collection 查询。
4. 删除缓存时同步清空 `vector_id` 并删除 Qdrant point。

## 验证命令

改动后至少运行：

```bash
rg -n "milvus|Milvus|MILVUS|pymilvus|langchain-milvus|milvus_id|ENABLE_EXTRA_MCP_TOOLS" --glob '!*.pyc' --glob '!__pycache__/**' .
python -m compileall internal pkg api scripts main.py
python -m unittest tests/test_qdrant_client_wrapper.py
cd web/plantform_vue && npm run build
```

当前已验证结果：

- Milvus 关键字静态搜索无命中。
- Python compileall 通过。
- Qdrant wrapper unittest 通过。
- 前端 Vite build 通过，仅有 chunk 体积提示。

## 登录与对话验证

本地验证使用账号：

```txt
admin / 123456
```

已确认：

- `/users/login` 能返回 `登录成功` 和 token。
- 前端能进入 `/chat`，顶部显示 `admin`。
- `/messages` 流式对话接口能创建会话、保存用户消息、返回 AI 回复、保存 AI 消息并发送 `done` 事件。
- `show_thinking=false` 已修正为真正的布尔值，不会再因为字符串 `"false"` 被 Python 当成真而强制输出思考、操作、观察事件。
- 前端聊天面板本身保留思考、操作、观察渲染能力，是否展示取决于前端发送的 `show_thinking`。

本地没有 Qdrant 时，登录和普通对话不应被 Qdrant 启动失败阻塞；服务器已配置 Qdrant 时按环境变量连接使用。

## 注意事项

- 不要把 `vector_id` 改回 `milvus_id`。
- 不要恢复 `internal/db/milvus.py`、`internal/db/milvus_config.py` 或 `milvus/docker-compose.yml`。
- 不要重新加 `ENABLE_EXTRA_MCP_TOOLS`，用户要求自定义工具限制已经解除。
- 如果要做真实接口复测，需要本机 MongoDB、Redis、Qdrant 服务已启动。
- `scripts/import_knowledge_snapshot.py` 当前只导入 `type=qdrant` 的快照向量；旧 Milvus 快照不作为默认兼容目标。
- 业务文案和前端页面应使用“Qdrant”或“向量库”，不要出现 Milvus。

# LangChain 改造任务列表

## ✅ 已完成
- [x] 1. `internal/llm/llm_service.py` - 使用 LangChain 的 ChatMessageHistory 和消息类型
- [x] 2. `internal/agent/react_agent.py` - 改用 LangChain 的 create_react_agent
- [x] 3. `internal/chat_service/chat_service.py` - 适配 LangChain Agent
- [x] 4. `internal/rag/rag_service.py` - 使用 LangChain 的 RAG 组件（VectorStoreRetriever）
- [x] 5. `pkg/agent_tools_mcp/` - 所有工具改造为 FastMCP 服务
  - [x] knowledge_search_mcp.py
  - [x] weather_query_mcp.py
  - [x] web_search_mcp.py
  - [x] email_sender_mcp.py
  - [x] geocode_mcp.py
  - [x] ip_location_mcp.py
  - [x] poi_search_mcp.py
  - [x] route_planning_mcp.py
- [x] MCP 管理器和配置
  - [x] mcp_config.py - 工具配置列表
  - [x] mcp_manager.py - 服务管理器
- [x] main.py - 启动时自动初始化 MCP 服务

## ⏳ 待完成
- [ ] 6. 测试所有 MCP 工具集成

## 📝 详细说明

### 2. Agent 改造
- 使用 `langchain.agents.create_react_agent`
- 使用 `AgentExecutor` 执行
- 保留回调机制（用于流式输出）
- 工具格式转换为 LangChain Tool

### 3. ChatService 改造
- 适配新的 Agent 接口
- 保持 Session 和 Redis 管理不变
- 调整 Agent 调用方式

### 4. RAG 改造
- 使用 `VectorStoreRetriever` 替代手动检索
- 使用 `Milvus` LangChain 集成
- 保留 Reranker 和去重逻辑

### 5. 工具改造为 MCP
- 每个工具文件改为 FastMCP 服务
- 保持工具函数签名不变
- 添加 `if __name__ == "__main__": app.run(transport='stdio')`

### 6. MCP 集成
- 在 message_sever.py 中启动 MCP 客户端
- 使用 `langchain_mcp_adapters.tools.load_mcp_tools`
- 传递给 Agent

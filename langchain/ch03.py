# react范式
OPENAI_API_KEY="sk-6fc6f53cc4584663b7926f469f4b4a4d"
base_url="https://api.deepseek.com"

from langchain_openai import ChatOpenAI
from langchain_mcp_adapters.tools import load_mcp_tools
from langchain.agents import create_agent
from fastapi import APIRouter, Request, FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from contextlib import asynccontextmanager

# 初始化 LLM
llm = ChatOpenAI(
    model="deepseek-chat",
    openai_api_key=OPENAI_API_KEY,
    openai_api_base=base_url,
    temperature=0.3,
    max_tokens=2048,
    stream_usage=True
)
# from langchain_community.llms import Ollama
# llm = Ollama(base_url="http://localhost:11434",model="llama3.2")
# MCP 工具配置
tools_path=[
    '/Users/haogeng/Desktop/genghao/work2/worktest/plantform/langchain/tools/web_search.py',
    '/Users/haogeng/Desktop/genghao/work2/worktest/plantform/langchain/tools/weather_query.py'
]

# 为每个工具创建服务器参数
server_params_list = [
    StdioServerParameters(
        command='/Users/haogeng/miniforge3/envs/langchain/bin/python',
        args=[tool_path],
    ) for tool_path in tools_path
]

# 全局变量
mcp_clients = []
mcp_sessions = []
tools = []

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时初始化 MCP
    global mcp_clients, mcp_sessions, tools
    print("🚀 启动多个 MCP 连接...")
    
    # 为每个工具启动独立的 MCP 服务器
    for i, server_params in enumerate(server_params_list):
        print(f"🔧 启动工具服务器 {i+1}/{len(server_params_list)}: {tools_path[i]}")
        
        mcp_client = stdio_client(server_params)
        read, write = await mcp_client.__aenter__()
        mcp_session = ClientSession(read, write)
        await mcp_session.__aenter__()
        await mcp_session.initialize()
        
        # 加载当前服务器的工具
        server_tools = await load_mcp_tools(mcp_session)
        tools.extend(server_tools)
        
        # 保存客户端和会话
        mcp_clients.append(mcp_client)
        mcp_sessions.append(mcp_session)
    
    print(f"✅ 所有 MCP 工具加载成功: {[t.name for t in tools]}")
    
    yield
    
    # 关闭时清理所有 MCP 连接
    print("🔄 关闭所有 MCP 连接...")
    for i, (session, client) in enumerate(zip(mcp_sessions, mcp_clients)):
        print(f"🔄 关闭连接 {i+1}/{len(mcp_sessions)}")
        if session:
            await session.__aexit__(None, None, None)
        if client:
            await client.__aexit__(None, None, None)

# 创建 FastAPI 应用
app = FastAPI(lifespan=lifespan)
router = APIRouter()

template = """Answer the following questions as best you can. You have access to the following tools:

{tools}

Use the following format:

Question: the input question you must answer
Thought: you should always think about what to do
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat N times)
Thought: I now know the final answer
Final Answer: the final answer to the original input question

Begin!

Question: {input}
Thought:{agent_scratchpad}"""
    


class QueryRequest(BaseModel):
    query: str

@router.post("/query")
async def query(request: QueryRequest):
    """使用 ReAct Agent 处理查询（流式返回）"""
    async def generate():
        try:
            # 在请求时创建 Agent（确保工具已加载）
            if not tools:
                yield "工具未加载，请稍后重试"
                return
                
            agent = create_agent(llm, tools, system_prompt=template)
            
            # 流式执行 Agent - 展示 ReAct 思考过程
            async for chunk in agent.astream({"messages": [("user", request.query)]}):
                print(f"Chunk: {chunk}")  # 调试信息
                
                # 处理 Agent 的思考和行动步骤
                for node_name, node_data in chunk.items():
                    if "messages" in node_data:
                        for message in node_data["messages"]:
                            if hasattr(message, 'content') and message.content:
                                # 根据节点类型添加标识
                                if node_name == "agent":
                                    yield f"\n🤔 **思考**: "
                                elif node_name == "tools":
                                    yield f"\n🔧 **工具执行结果**: "
                                else:
                                    yield f"\n📝 **{node_name}**: "
                                
                                # 逐字符流式输出内容
                                for char in message.content:
                                    print(message)
                                    yield char
                                    
                                yield "\n"  # 每个步骤后换行
                
        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            print(f"详细错误: {error_detail}")
            yield f"处理失败: {str(e)}\n详细错误: {error_detail}"
    
    return StreamingResponse(generate(), media_type="text/plain")


# 注册路由
app.include_router(router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8081)

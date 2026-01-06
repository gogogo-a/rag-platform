"""
测试 MCP 工具是否能正常返回数据
"""
import asyncio
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def test_web_search():
    """测试 web_search MCP 工具"""
    print("=" * 60)
    print("测试 web_search MCP 工具")
    print("=" * 60)
    
    # 配置 MCP 服务器
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["pkg/agent_tools_mcp/web_search_mcp.py"]
    )
    
    try:
        # 启动客户端
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                # 初始化
                await session.initialize()
                print("✅ MCP 会话已初始化")
                
                # 列出工具
                tools = await session.list_tools()
                print(f"✅ 可用工具: {[t.name for t in tools.tools]}")
                
                # 调用工具
                print("\n调用 web_search 工具...")
                result = await session.call_tool(
                    "web_search",
                    arguments={
                        "query": "人工智能",
                        "max_results": 3,
                        "search_recency": "week"
                    }
                )
                
                print(f"\n返回结果类型: {type(result)}")
                print(f"是否有 content: {hasattr(result, 'content')}")
                
                if hasattr(result, 'content'):
                    print(f"content 类型: {type(result.content)}")
                    print(f"content 长度: {len(result.content) if result.content else 0}")
                    
                    if result.content:
                        print(f"\n第一个 content 项:")
                        first = result.content[0]
                        print(f"  类型: {type(first)}")
                        print(f"  是否有 text: {hasattr(first, 'text')}")
                        
                        if hasattr(first, 'text'):
                            text = first.text
                            print(f"  文本长度: {len(text)}")
                            print(f"  文本内容（前200字符）:\n{text[:200]}")
                        else:
                            print(f"  内容: {first}")
                else:
                    print(f"完整结果: {result}")
                
                print("\n✅ 测试完成")
                
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_web_search())

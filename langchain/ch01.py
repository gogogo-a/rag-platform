# 流式返回
import os
OPENAI_API_KEY="sk-6fc6f53cc4584663b7926f469f4b4a4d"
base_url="https://api.deepseek.com"

from langchain_openai import ChatOpenAI
llm = ChatOpenAI(
                model="deepseek-chat",
                openai_api_key=OPENAI_API_KEY,
                openai_api_base=base_url,
                temperature=0.3,
                max_tokens=1024,
                stream_usage=True
            )
# 流式返回方式
for chunk in llm.stream("人工智能是什么,10个字回答我"):
    print(chunk.content, end="", flush=True)
print()  # 换行
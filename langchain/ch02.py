# web流式返回
import os
OPENAI_API_KEY="sk-6fc6f53cc4584663b7926f469f4b4a4d"
base_url="https://api.deepseek.com"

from langchain_openai import ChatOpenAI
from fastapi import APIRouter, Query, Request, FastAPI
from fastapi.responses import StreamingResponse
app = FastAPI()
router = APIRouter()
llm = ChatOpenAI(
                model="deepseek-chat",
                openai_api_key=OPENAI_API_KEY,
                openai_api_base=base_url,
                temperature=0.3,
                max_tokens=1024,
                stream_usage=True
            )
# 流式返回方式
@router.post("/query")
def query (query :str="人工智能是什么"):
    def generate():
        for chunk in llm.stream(query):
            if chunk.content:
                yield chunk.content
    return StreamingResponse(generate())

# 注册路由
app.include_router(router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8082)

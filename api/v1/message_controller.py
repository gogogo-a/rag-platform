"""
消息管理 API 控制器 (RESTful 风格)
集成 Agent + RAG 检索
统一流式返回
支持文件上传
"""
from fastapi import APIRouter, Query, Path, Request, Form, File, UploadFile
from fastapi.responses import StreamingResponse
from internal.dto.request import SendMessageRequest
from internal.service.orm.message_sever import message_service
from internal.service.message.context_usage_service import context_usage_service
from api.v1.response_controller import json_response
from pkg.middleware.auth import get_user_from_request
from internal.document_client.document_extract import extract_document_content
from log import logger
import json as json_module
from typing import Optional
from pathlib import Path as PathlibPath
from pkg.constants.constants import SUPPORTED_IMAGE_FORMATS
# 使用全局JWT中间件，不需要路由级别的dependencies
router = APIRouter(
    prefix="/messages", 
    tags=["消息管理"]
)


@router.post("", summary="发送消息并获取 AI 回复（统一流式返回，支持文件上传）")
async def send_message(
    request: Request,
    content: str = Form(..., description="消息内容"),
    session_id: Optional[str] = Form(None, description="会话ID（可选）"),
    send_name: Optional[str] = Form(None, description="发送者昵称（可选）"),
    send_avatar: Optional[str] = Form(None, description="发送者头像URL（可选）"),
    show_thinking: str = Form("false", description="是否显示思考过程"),
    agent_mode: str = Form("single", description="Agent 模式：single 或 expert"),
    location: Optional[str] = Form(None, description="用户位置信息（JSON字符串，包含经纬度等）"),
    skip_cache: str = Form("false", description="是否跳过缓存（重新回答时使用）"),
    regenerate_message_id: Optional[str] = Form(None, description="重新生成时的原消息ID（用于删除旧缓存）"),
    file: Optional[UploadFile] = File(None, description="上传的文件（可选，支持文档和图片：.pdf/.docx/.pptx/.xlsx/.csv/.html/.txt/.md/.rtf/.epub/.json/.xml/.jpg/.jpeg/.png/.webp/.gif/.bmp/.tiff）")
):
    """
    发送消息并自动获取 AI 智能回复（统一流式返回，支持文件和图片上传）
    
    **参数：**
    - **content**: 消息内容（必填）
    - **session_id**: 会话ID（可选，不提供则创建新会话）
    - **send_name**: 发送者昵称（可选，使用token中的昵称）
    - **send_avatar**: 发送者头像URL（可选）
    - **show_thinking**: 是否显示思考过程（默认 False）
    - **location**: 用户位置信息（可选，JSON字符串，包含经纬度等）
    - **skip_cache**: 是否跳过缓存（重新回答时使用，默认 False）
    - **regenerate_message_id**: 重新生成时的原消息ID（用于删除旧缓存）
    - **file**: 上传的文件（可选，支持文档和图片格式）
    
    **文件上传说明：**
    如果上传了文件，系统会：
    1. **文档文件**（PDF、Word、PowerPoint 等）：解析文档内容，提取文字和表格
    2. **图片文件**（JPG、PNG、WebP 等）：使用 OCR 识别图片中的文字 ⭐
    3. 在消息中添加文件类型提示："这是我上传的 xxx 文件/图片..."
    4. 将文件内容/识别结果保存到消息的 extra_data 中
    5. AI 会基于文件内容/图片识别结果回答问题
    
    **返回格式：**
    统一使用 SSE（Server-Sent Events）流式返回
    
    **SSE 事件类型：**
    - `session_created`: 会话创建
    - `user_message_saved`: 用户消息保存完成
    - `thought`: Agent 思考过程（仅 show_thinking=True）
    - `action`: Agent 执行动作（仅 show_thinking=True）
    - `observation`: 观察结果（仅 show_thinking=True）
    - `answer_chunk`: 最终答案片段（流式输出）
    - `documents`: 检索到的文档列表（包含 uuid 和 name，已去重）
    - `ai_message_saved`: AI 消息保存完成
    - `done`: 完成
    - `error`: 错误
    
    **使用示例（Python - 不带文件）：**
    ```python
    import requests
    
    response = requests.post(
        "http://localhost:8000/messages",
        data={
            "content": "你好",
            "show_thinking": "false"
        },
        headers={"Authorization": "Bearer <token>"},
        stream=True
    )
    ```
    
    **使用示例（Python - 带文档文件）：**
    ```python
    import requests
    
    with open("document.pdf", "rb") as f:
        response = requests.post(
            "http://localhost:8000/messages",
            data={
                "content": "请总结这个文档的主要内容",
                "show_thinking": "true"
            },
            files={"file": ("document.pdf", f, "application/pdf")},  # 注意：字段名是 'file'
            headers={"Authorization": "Bearer <token>"},
            stream=True
        )
    ```
    
    **使用示例（Python - 带图片文件）：** ⭐
    ```python
    import requests
    
    with open("screenshot.png", "rb") as f:
        response = requests.post(
            "http://localhost:8000/messages",
            data={
                "content": "这张图片里有什么内容？帮我识别一下",
                "show_thinking": "false"
            },
            files={"file": ("screenshot.png", f, "image/png")},  # 支持 jpg/png/webp 等
            headers={"Authorization": "Bearer <token>"},
            stream=True
        )
    ```
    """
    try:
        # 验证必填参数
        if not content:
            logger.error("❌ content 参数缺失或为空")
            return json_response("消息内容不能为空", -1)
        
        # 从全局中间件中获取用户信息
        logger.debug(f"开始获取用户信息, request.state: {hasattr(request.state, 'user')}")
        try:
            current_user = get_user_from_request(request)
            logger.debug(f"用户信息获取成功: {current_user}")
        except Exception as auth_error:
            logger.error(f"获取用户信息失败: {auth_error}", exc_info=True)
            raise
        
        user_id = current_user.get("user_id")
        user_nickname = current_user.get("nickname", "用户")
        
        # 🔥 Controller 层职责：文件读取（不做解析，交给 Service 层流式处理）
        file_content = None
        file_type = None
        file_name = None
        file_size = None
        file_bytes = None
        
        # 处理文件上传
        if file:
            logger.info(f"检测到文件上传: {file.filename}, content_type={file.content_type}")
            
            try:
                # 1. 读取文件字节流
                file_bytes = await file.read()
                file_size = str(len(file_bytes))
                file_name = file.filename
                
                # 2. 确定文件类型（自动从扩展名推断）
                extension = PathlibPath(file_name).suffix.lower()
                file_type = extension[1:] if extension else 'file'
                
                # 3. 判断是图片还是文档
                if extension in SUPPORTED_IMAGE_FORMATS:
                    # 🖼️ 图片文件：不在这里处理，传递给 Service 层流式处理
                    logger.info(f"🖼️ 检测到图片文件: {file_name}，将在 Service 层流式分析")
                else:
                    # 📄 文档文件：立即解析（文档解析不需要流式）
                    logger.info(f"📄 检测到文档文件，提取文本内容")
                    file_content = extract_document_content(file_bytes, file_name)
                    logger.info(f"✅ 文档解析成功: type={file_type}, size={file_size}, content_length={len(file_content)}")
                
            except Exception as e:
                logger.error(f"文件处理失败: {e}", exc_info=True)
                return json_response(f"文件处理失败: {str(e)}", -1)
        
        show_thinking_enabled = show_thinking.lower() == "true"
        normalized_agent_mode = agent_mode.lower().strip()
        if normalized_agent_mode not in {"single", "expert"}:
            normalized_agent_mode = "single"
        logger.info(f"收到发送消息请求: user={user_id}, nickname={user_nickname}, session={session_id}, show_thinking={show_thinking_enabled}, has_file={file is not None}")
        
        async def event_generator():
            """SSE 事件生成器（在 Controller 层格式化）"""
            try:
                async for event in message_service.send_message_stream(
                    content=content,  # 🔥 原始用户问题（保存到数据库）
                    user_id=user_id,
                    send_name=send_name or user_nickname,
                    send_avatar=send_avatar or "",
                    session_id=session_id,
                    file_type=file_type,
                    file_name=file_name,
                    file_size=file_size,
                    file_content=file_content,  # 🔥 文档内容（已解析）
                    file_bytes=file_bytes,  # 🔥 图片字节流（未解析，Service 层流式处理）
                    show_thinking=show_thinking_enabled,
                    agent_mode=normalized_agent_mode,
                    location=location,  # 🔥 用户位置信息（GPS 经纬度，用于 POI 搜索、天气查询、路线规划等）
                    skip_cache=skip_cache.lower() == "true",  # 🔥 是否跳过缓存
                    regenerate_message_id=regenerate_message_id  # 🔥 重新生成时的原消息ID
                ):
                    # 格式化为 SSE 格式
                    event_type = event.get("event", "message")
                    event_data = event.get("data", {})
                    
                    # SSE 格式: event: <type>\ndata: <json>\n\n
                    yield f"event: {event_type}\n"
                    yield f"data: {json_module.dumps(event_data, ensure_ascii=False)}\n\n"
                    
            except Exception as e:
                logger.error(f"流式生成失败: {e}", exc_info=True)
                yield f"event: error\n"
                yield f"data: {json_module.dumps({'message': str(e)}, ensure_ascii=False)}\n\n"
        
        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"  # 禁用 Nginx 缓冲
            }
        )
        
    except Exception as e:
        logger.error(f"发送消息失败: {e}", exc_info=True)
        return json_response("系统错误", -1)


@router.get("/{session_id}/context-usage", summary="获取会话上下文占用")
async def get_session_context_usage(
    request: Request,
    session_id: str = Path(..., description="会话UUID")
):
    try:
        current_user = get_user_from_request(request)
        if current_user.get("is_admin") != 1:
            return json_response("无权限", -2, status_code=403)

        data = await context_usage_service.get_session_context_usage(session_id)
        return json_response("查询成功", 0, data)

    except Exception as e:
        logger.error(f"获取上下文占用失败: {e}", exc_info=True)
        return json_response("系统错误", -1)


@router.get("/{session_id}", summary="获取会话的所有消息")
async def get_session_messages(
    session_id: str = Path(..., description="会话UUID"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=50, ge=1, le=200, description="每页数量")
):
    try:
        logger.info(f"收到获取会话消息请求: session={session_id}, page={page}, page_size={page_size}")
        
        message, ret, data = await message_service.get_session_messages(
            session_id=session_id,
            page=page,
            page_size=page_size
        )
        
        if data:
            return json_response(message, ret, data)
        return json_response(message, ret)
        
    except Exception as e:
        logger.error(f"获取会话消息失败: {e}", exc_info=True)
        return json_response("系统错误", -1)


@router.post("/feedback", summary="提交消息反馈（点赞/踩）")
async def submit_feedback(
    request: Request,
    thought_chain_id: str = Form(..., description="思维链ID"),
    feedback_type: str = Form(..., description="反馈类型：like（点赞）或 dislike（踩）")
):
    """
    提交消息反馈（点赞/踩）
    
    用于收集用户对 AI 回答的反馈，影响缓存策略：
    - 点赞：增加该回答的权重，更容易被相似问题命中
    - 踩：减少该回答的权重，累计 3 次踩后自动删除缓存
    
    **参数：**
    - **thought_chain_id**: 思维链ID（从 AI 消息的 extra_data 中获取）
    - **feedback_type**: 反馈类型，只能是 "like" 或 "dislike"
    
    **返回：**
    - success: 是否成功
    - like_count: 当前点赞数
    - dislike_count: 当前踩数
    - is_cached: 是否仍在缓存中
    """
    try:
        # 验证反馈类型
        if feedback_type not in ["like", "dislike"]:
            return json_response("反馈类型无效，只能是 like 或 dislike", -1)
        
        # 从全局中间件中获取用户信息（验证登录状态）
        try:
            current_user = get_user_from_request(request)
            user_id = current_user.get("user_id")
        except Exception as auth_error:
            logger.error(f"获取用户信息失败: {auth_error}")
            return json_response("未授权", -1)
        
        # 调用缓存服务更新反馈
        from internal.service.ai.similar_qa_cache import similar_qa_cache
        
        result = await similar_qa_cache.update_feedback(
            thought_chain_id=thought_chain_id,
            feedback_type=feedback_type,
            user_id=user_id  # 传递用户ID防止重复操作
        )
        
        if result.get("success"):
            logger.info(f"反馈提交成功: thought_chain={thought_chain_id}, type={feedback_type}")
            return json_response("反馈提交成功", 0, {
                "like_count": result.get("like_count", 0),
                "dislike_count": result.get("dislike_count", 0),
                "is_cached": result.get("is_cached", False)
            })
        else:
            return json_response(result.get("message", "反馈提交失败"), -1)
        
    except Exception as e:
        logger.error(f"提交反馈失败: {e}", exc_info=True)
        return json_response("系统错误", -1)


@router.delete("/cache/{thought_chain_id}", summary="删除指定的 QA 缓存")
async def delete_qa_cache(
    request: Request,
    thought_chain_id: str = Path(..., description="思维链ID")
):
    """
    删除指定的 QA 缓存
    
    用于手动删除不准确的缓存回答
    
    **参数：**
    - **thought_chain_id**: 思维链ID
    
    **返回：**
    - success: 是否删除成功
    """
    try:
        # 从全局中间件中获取用户信息（验证登录状态）
        try:
            current_user = get_user_from_request(request)
        except Exception as auth_error:
            logger.error(f"获取用户信息失败: {auth_error}")
            return json_response("未授权", -1)
        
        # 调用缓存服务删除缓存
        from internal.service.ai.similar_qa_cache import similar_qa_cache
        
        success = await similar_qa_cache.delete_cache(thought_chain_id)
        
        if success:
            logger.info(f"缓存删除成功: thought_chain={thought_chain_id}")
            return json_response("缓存删除成功", 0)
        else:
            return json_response("缓存删除失败", -1)
        
    except Exception as e:
        logger.error(f"删除缓存失败: {e}", exc_info=True)
        return json_response("系统错误", -1)

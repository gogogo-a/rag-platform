"""
文档管理 API 控制器 (RESTful 风格)
提供文档上传、删除、查询、列表等接口
"""
from typing import List
from fastapi import APIRouter, UploadFile, File, Query, Path, Request, Form

from internal.service.orm.document_sever import document_service
from api.v1.response_controller import json_response
from pkg.middleware.auth import get_user_from_request
from log import logger

router = APIRouter(prefix="/documents", tags=["文档管理"])


@router.post("", summary="上传文档（支持批量）")
async def upload_document(
    request: Request,
    files: List[UploadFile] = File(..., description="文档文件列表（支持单个或多个文件）"),
    permission: int = Form(default=0, description="文档权限：0=普通用户可见，1=仅管理员可见")
):
    """
    上传文档并自动进行 Embedding 处理（支持批量上传）
    
    - **files**: 文档文件列表（支持 .pdf, .docx, .pptx, .doc, .ppt, .txt, .md, .xlsx, .csv, .html, .rtf, .epub, .json, .xml）- 可以上传单个或多个文件
    - **permission**: 文档权限（0=普通用户可见，1=仅管理员可见）- 所有文件共享此权限
    
    处理流程：
    1. 保存文件到本地
    2. 记录到 MongoDB（包含 permission）
    3. 提交到 Kafka 进行异步 Embedding
    4. 存储向量到 Qdrant（后台处理，元数据包含 permission）
    
    返回格式：
    - 单个文件：返回单个文档信息
    - 多个文件：返回文档列表，包含每个文件的处理结果
    """
    try:
        # 获取用户信息
        user = get_user_from_request(request)
        
        logger.info(f"收到上传请求: 用户={user.get('nickname')}, 文件数={len(files)}, 权限={permission}")
        
        # 验证文件类型
        allowed_extensions = [
            '.pdf', '.docx', '.pptx', '.doc', '.ppt', 
            '.txt', '.md', '.xlsx', '.csv', '.html', 
            '.rtf', '.epub', '.json', '.xml'
        ]
        
        # 存储所有结果
        results = []
        success_count = 0
        failed_count = 0
        
        # 逐个处理文件
        for file in files:
            try:
                logger.info(f"处理文件: {file.filename}, 类型: {file.content_type}")
                
                # 验证文件类型
                file_ext = file.filename[file.filename.rfind('.'):].lower()
                
                if file_ext not in allowed_extensions:
                    failed_count += 1
                    results.append({
                        "filename": file.filename,
                        "success": False,
                        "message": f"不支持的文件类型: {file_ext}，支持的类型: {', '.join(allowed_extensions)}",
                        "ret": -2
                    })
                    continue
                
                # 调用业务逻辑
                message, ret, data = await document_service.upload_document(
                    file=file,
                    permission=permission,
                    uploader_id=user.get('user_id'),
                    uploader_name=user.get('nickname')
                )
                
                if ret == 0:
                    success_count += 1
                    results.append({
                        "filename": file.filename,
                        "success": True,
                        "message": message,
                        "ret": ret,
                        "data": data
                    })
                else:
                    failed_count += 1
                    results.append({
                        "filename": file.filename,
                        "success": False,
                        "message": message,
                        "ret": ret
                    })
                    
            except Exception as e:
                failed_count += 1
                logger.error(f"处理文件 {file.filename} 失败: {e}", exc_info=True)
                results.append({
                    "filename": file.filename,
                    "success": False,
                    "message": f"处理失败: {str(e)}",
                    "ret": -1
                })
        
        # 返回结果
        if len(files) == 1:
            # 单个文件：返回单个结果（保持向后兼容）
            result = results[0]
            if result["success"]:
                return json_response(result["message"], result["ret"], result.get("data"))
            else:
                return json_response(result["message"], result["ret"])
        else:
            # 多个文件：返回批量结果
            return json_response(
                f"批量上传完成：成功 {success_count} 个，失败 {failed_count} 个",
                0 if failed_count == 0 else -1,
                {
                    "total": len(files),
                    "success_count": success_count,
                    "failed_count": failed_count,
                    "results": results
                }
            )
        
    except Exception as e:
        logger.error(f"上传文档失败: {e}", exc_info=True)
        return json_response("系统错误", -1)


@router.get("", summary="获取文档列表")
async def get_document_list(
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=10, ge=1, le=100, description="每页数量"),
    keyword: str = Query(default=None, description="搜索关键词（文档名称）")
):
    """
    获取文档列表（分页 + 搜索）
    
    - **page**: 页码（从1开始）
    - **page_size**: 每页数量（最大100）
    - **keyword**: 搜索关键词（可选，模糊匹配文档名称）
    
    返回每个文档的元数据：
    - uuid: 文档唯一标识
    - name: 文档名称
    - uploaded_at: 上传时间
    - chunk_count: 文本块数量（从 Qdrant 查询）
    """
    try:
        logger.info(f"收到文档列表请求: page={page}, page_size={page_size}, keyword={keyword}")
        message, ret, data = await document_service.get_document_list(
            page=page,
            page_size=page_size,
            keyword=keyword
        )
        
        if data:
            return json_response(message, ret, data)
        return json_response(message, ret)
        
    except Exception as e:
        logger.error(f"获取文档列表失败: {e}", exc_info=True)
        return json_response("系统错误", -1)


@router.post("/{document_id}/retry", summary="重新处理文档")
async def retry_document_processing(
    document_id: str = Path(..., description="文档UUID")
):
    try:
        message, ret, data = await document_service.retry_document_processing(document_id)
        if data:
            return json_response(message, ret, data)
        return json_response(message, ret)
    except Exception as e:
        logger.error(f"重新处理文档失败: {e}", exc_info=True)
        return json_response("系统错误", -1)


@router.get("/{document_id}", summary="获取文档详情")
async def get_document_detail(
    document_id: str = Path(..., description="文档UUID")
):
    """
    获取文档详情
    
    - **document_id**: 文档UUID
    
    返回文档的完整信息：
    - uuid: 文档唯一标识
    - name: 文档名称
    - size: 文件大小（字节）
    - page: 文档页数
    - url: 文档访问URL
    - uploaded_at: 上传时间
    - chunk_count: 文本块数量（从 Qdrant 查询）
    """
    try:
        logger.info(f"收到文档详情请求: {document_id}")
        message, ret, data = await document_service.get_document_detail(document_id)
        
        if data:
            return json_response(message, ret, data)
        return json_response(message, ret)
        
    except Exception as e:
        logger.error(f"获取文档详情失败: {e}", exc_info=True)
        return json_response("系统错误", -1)


@router.delete("/{document_id}", summary="删除文档")
async def delete_document(
    document_id: str = Path(..., description="文档UUID")
):
    """
    删除文档（包括 MongoDB 记录、Qdrant 向量、物理文件）
    
    - **document_id**: 文档UUID
    """
    try:
        logger.info(f"收到删除请求: {document_id}")
        message, ret = await document_service.delete_document(document_id)
        return json_response(message, ret)
        
    except Exception as e:
        logger.error(f"删除文档失败: {e}", exc_info=True)
        return json_response("系统错误", -1)

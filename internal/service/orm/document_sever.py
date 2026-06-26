"""
文档服务业务逻辑层
处理文档的上传、查询、删除等业务
"""
import uuid as uuid_module
import hashlib
from typing import Dict, Any, Optional
from pathlib import Path
from fastapi import UploadFile
from pydantic import BaseModel
from internal.model.document import DocumentModel
from internal.model.chunk import ChunkModel
from internal.db.qdrant import qdrant_client
from internal.document_client.document_processor import document_processor
from internal.document_client.config_loader import config
from pkg.constants.constants import QDRANT_COLLECTION_NAME
from log import logger


class DocumentListItem(BaseModel):
    uuid: str
    name: str
    page: int = 0
    size: int
    status: int = 0
    permission: int = 0
    extra_data: Dict[str, Any] = {}
    create_at: Optional[Any] = None
    update_at: Optional[Any] = None


class DocumentService:
    """文档服务类"""

    def __init__(self):
        self.upload_dir = Path("uploads")
        self.upload_dir.mkdir(exist_ok=True)
        self.collection_name = QDRANT_COLLECTION_NAME

    def _calculate_file_sha256(self, file_content: bytes) -> str:
        return hashlib.sha256(file_content).hexdigest()

    async def _find_existing_document_by_hash(self, file_sha256: str, permission: int):
        if not file_sha256:
            return None
        docs = await DocumentModel.find({
            "extra_data.file_sha256": file_sha256,
            "permission": permission,
            "status": {"$in": [1, 2]},
        }).to_list()
        return docs[0] if docs else None

    def _build_duplicate_upload_response(self, existing_doc, original_filename: str) -> Dict[str, Any]:
        chunk_count = self._get_saved_chunk_count(existing_doc)
        return {
            "uuid": existing_doc.uuid,
            "name": existing_doc.name,
            "size": existing_doc.size,
            "page": existing_doc.page,
            "url": existing_doc.url,
            "content": "",
            "content_length": 0,
            "status": existing_doc.status,
            "status_text": "处理中" if existing_doc.status == 1 else "处理完成",
            "permission": existing_doc.permission,
            "chunk_count": chunk_count,
            "dedup_status": "duplicate",
            "original_document_uuid": existing_doc.uuid,
            "original_filename": original_filename,
            "message": "文档已存在"
        }

    def _build_processing_task(self, document_uuid: str, file_path: Path, permission: int, uploader_id: str = None, uploader_name: str = None):
        return {
            "task_type": "file",
            "file_path": str(file_path),
            "document_uuid": document_uuid,
            "permission": permission,
            "metadata": {
                "filename": file_path.name,
                "source": "api_upload",
                "permission": permission,
                "uploader_id": uploader_id,
                "uploader_name": uploader_name
            }
        }

    def _merge_extra_data(self, doc, update: Dict[str, Any]):
        current_extra_data = getattr(doc, "extra_data", None)
        extra_data = dict(current_extra_data) if isinstance(current_extra_data, dict) else {}
        extra_data.update(update)
        doc.extra_data = extra_data
        return extra_data

    async def upload_document(
        self,
        file: UploadFile,
        permission: int = 0,
        uploader_id: str = None,
        uploader_name: str = None
    ):
        """
        上传文档并异步处理

        Args:
            file: 上传的文件
            permission: 文档权限（0=普通用户可见，1=仅管理员可见）
            uploader_id: 上传者ID
            uploader_name: 上传者名称

        Returns:
            tuple: (message, ret, data) - message: 提示信息, ret: 返回码(0成功/-1失败), data: 文档信息
        """
        try:
            from datetime import datetime
            # 1. 读取文件并检查重复上传
            file_content = await file.read()
            file_sha256 = self._calculate_file_sha256(file_content)
            existing_doc = await self._find_existing_document_by_hash(file_sha256, permission)
            if existing_doc:
                data = self._build_duplicate_upload_response(existing_doc, file.filename)
                return "文档已存在", 0, data

            # 2. 生成唯一文件名（使用 UUID 确保唯一性）
            file_uuid = str(uuid_module.uuid4())  # 生成全局唯一标识符
            file_extension = Path(file.filename).suffix  # 保留原始文件扩展名
            new_filename = f"{file_uuid}{file_extension}"  # 格式：UUID.扩展名（如：a1b2c3d4-e5f6-7g8h-9i0j-k1l2m3n4o5p6.pdf）
            file_path = self.upload_dir / new_filename

            logger.info(f"生成唯一文件名: {file.filename} → {new_filename}")

            # 3. 保存文件到服务器
            with open(file_path, "wb") as f:
                f.write(file_content)

            file_size = len(file_content)
            logger.info(f"文件已保存: {file_path}, 大小: {file_size} bytes")

            # 4. 保存文档信息到 MongoDB（初始状态：未处理）
            upload_time = datetime.now()
            doc_model = DocumentModel(
                uuid=file_uuid,
                name=file.filename,
                content="",
                page=0,
                url=f"/uploads/{new_filename}",
                size=file_size,
                status=0,  # 0.未处理
                permission=permission,  # 🔥 文档权限
                extra_data={  # 🔥 额外数据
                    "uploader_id": uploader_id,
                    "uploader_name": uploader_name,
                    "upload_time": upload_time.isoformat(),
                    "file_extension": file_extension,
                    "file_sha256": file_sha256,
                    "original_filename": file.filename,
                    "dedup_status": "new"
                }
            )
            await doc_model.insert()

            logger.info(f"文档已保存到 MongoDB: {file_uuid}, 状态: 未处理")

            # 5. 提交到 Kafka 异步处理（Embedding）
            task = self._build_processing_task(file_uuid, file_path, permission, uploader_id, uploader_name)

            submit_success = document_processor.submit_task(task)

            if not submit_success:
                logger.error(f"任务提交失败: {file_uuid}")
                # 更新状态为处理失败
                doc_model.status = 3  # 3.处理失败
                self._merge_extra_data(doc_model, {
                    "processing_stage": "failed",
                    "failure_stage": "submit",
                    "failure_reason": "文档处理任务提交失败，请稍后重试",
                    "failed_at": datetime.now().isoformat(),
                    "retry_count": 0,
                })
                await doc_model.save()
                logger.info(f"文档状态已更新: {file_uuid} -> 处理失败")

                data = {
                    "uuid": file_uuid,
                    "name": file.filename,
                    "status": 3,
                    "status_text": "处理失败"
                }
                return "文档保存成功，但处理任务提交失败", -1, data

            # 更新状态为处理中
            doc_model.status = 1  # 1.处理中
            self._merge_extra_data(doc_model, {
                "processing_stage": "queued",
                "queued_at": datetime.now().isoformat(),
                "retry_count": 0,
            })
            await doc_model.save()
            logger.info(f"文档状态已更新: {file_uuid} -> 处理中")
            logger.info(f"文档处理任务已提交: {file_uuid}")

            data = {
                "uuid": file_uuid,
                "name": file.filename,
                "size": file_size,
                "page": 0,
                "url": f"/uploads/{new_filename}",
                "content": "",
                "content_length": 0,
                "status": 1,
                "status_text": "处理中",
                "permission": permission,  # 🔥 返回权限信息
                "dedup_status": "new",
                "processing_stage": "queued",
                "message": "文档已提交处理，后台正在进行 Embedding"
            }
            return "上传成功", 0, data

        except Exception as e:
            logger.error(f"上传文档失败: {e}", exc_info=True)
            return f"上传失败: {str(e)}", -1, None

    async def get_document_detail(self, document_uuid: str):
        """
        获取文档详情

        Args:
            document_uuid: 文档UUID

        Returns:
            tuple: (message, ret, data) - message: 提示信息, ret: 返回码, data: 文档详细信息
        """
        try:
            # 1. 从 MongoDB 获取文档基本信息
            doc = await DocumentModel.find_one(DocumentModel.uuid == document_uuid)

            if not doc:
                return "文档不存在", -2, None

            # 2. 使用文档记录中已保存的分块数量，避免详情请求实时扫描远程向量库
            chunk_count = self._get_saved_chunk_count(doc)

            # 3. 状态文本映射
            status_text_map = {
                0: "未处理",
                1: "处理中",
                2: "处理完成",
                3: "处理失败"
            }

            data = {
                "uuid": doc.uuid,
                "name": doc.name,
                "size": doc.size,
                "page": doc.page,
                "url": doc.url,
                "content": doc.content,  # 返回完整内容
                "content_length": len(doc.content) if doc.content else 0,
                "status": doc.status,
                "status_text": status_text_map.get(doc.status, "未知"),
                "permission": doc.permission,  # 🔥 返回权限信息
                "extra_data": doc.extra_data,  # 🔥 返回额外数据（上传者、处理时间等）
                "uploaded_at": doc.create_at.isoformat() if doc.create_at else None,
                "updated_at": doc.update_at.isoformat() if doc.update_at else None,  # 🔥 返回更新时间
                "chunk_count": chunk_count
            }
            return "查询成功", 0, data

        except Exception as e:
            logger.error(f"获取文档详情失败: {e}", exc_info=True)
            return f"查询失败: {str(e)}", -1, None

    async def delete_document(self, document_uuid: str):
        """
        删除文档（MongoDB + 向量库 + 物理文件）

        Args:
            document_uuid: 文档UUID

        Returns:
            tuple: (message, ret) - message: 提示信息, ret: 返回码
        """
        try:
            # 1. 查询文档
            doc = await DocumentModel.find_one(DocumentModel.uuid == document_uuid)

            if not doc:
                return "文档不存在", -2

            # 2. 删除 MongoDB 记录
            await doc.delete()
            logger.info(f"MongoDB 文档已删除: {document_uuid}")

            # 3. 删除向量数据
            deleted_count = self._delete_from_vector_store(document_uuid)
            logger.info(f"文档向量已删除: {document_uuid}, 数量: {deleted_count}")

            # 4. 删除物理文件
            file_path = Path(doc.url.lstrip('/'))
            if file_path.exists():
                file_path.unlink()
                logger.info(f"物理文件已删除: {file_path}")

            return f"文档已删除（包含 {deleted_count} 个向量块）", 0

        except Exception as e:
            logger.error(f"删除文档失败: {e}", exc_info=True)
            return f"删除失败: {str(e)}", -1

    async def get_document_list(
        self,
        page: int = 1,
        page_size: int = 10,
        keyword: Optional[str] = None
    ):
        """
        获取文档列表（分页 + 搜索）

        Args:
            page: 页码
            page_size: 每页数量
            keyword: 搜索关键词

        Returns:
            tuple: (message, ret, data) - message: 提示信息, ret: 返回码, data: 文档列表
        """
        try:
            # 1. 构建查询条件
            skip = (page - 1) * page_size

            if keyword:
                # 使用名称模糊搜索
                query = {"name": {"$regex": keyword, "$options": "i"}}
                total = await DocumentModel.find(query).count()
                docs = (
                    await DocumentModel.find(query, projection_model=DocumentListItem)
                    .sort(-DocumentModel.update_at)
                    .skip(skip)
                    .limit(page_size)
                    .to_list()
                )
            else:
                total = await DocumentModel.count()
                docs = (
                    await DocumentModel.find_all(projection_model=DocumentListItem)
                    .sort(-DocumentModel.update_at)
                    .skip(skip)
                    .limit(page_size)
                    .to_list()
                )

            # 2. 组装文档列表，优先使用已保存的分块数量
            status_text_map = {
                0: "未处理",
                1: "处理中",
                2: "处理完成",
                3: "处理失败"
            }

            document_list = []
            for doc in docs:
                chunk_count = self._get_saved_chunk_count(doc)
                extra_data = getattr(doc, "extra_data", None) or {}
                document_list.append({
                    "uuid": doc.uuid,
                    "name": doc.name,
                    "size": doc.size,  # 🔥 添加文件大小
                    "status": doc.status,
                    "status_text": status_text_map.get(doc.status, "未知"),
                    "permission": doc.permission,  # 🔥 添加权限信息
                    "uploaded_at": doc.create_at.isoformat() if doc.create_at else None,
                    "updated_at": doc.update_at.isoformat() if doc.update_at else None,
                    "chunk_count": chunk_count,
                    "failure_reason": extra_data.get("failure_reason"),
                    "failure_stage": extra_data.get("failure_stage"),
                    "processing_stage": extra_data.get("processing_stage"),
                    "retry_count": extra_data.get("retry_count", 0),
                })

            data = {
                "total": total,
                "page": page,
                "page_size": page_size,
                "documents": document_list
            }
            return "查询成功", 0, data

        except Exception as e:
            logger.error(f"获取文档列表失败: {e}", exc_info=True)
            return f"查询失败: {str(e)}", -1, None

    def _get_saved_chunk_count(self, doc) -> int:
        """
        从文档记录读取已保存的分块数量。
        """
        extra_data = getattr(doc, "extra_data", None) or {}
        chunks_count = extra_data.get("chunks_count")
        if isinstance(chunks_count, int) and chunks_count >= 0:
            return chunks_count
        page = getattr(doc, "page", 0) or 0
        if isinstance(page, int) and page >= 0:
            return page
        return 0

    async def retry_document_processing(self, document_uuid: str):
        try:
            from datetime import datetime

            doc = await DocumentModel.find_one(DocumentModel.uuid == document_uuid)
            if not doc:
                return "文档不存在", -2, None

            if doc.status not in (1, 3):
                return "当前文档不需要重新处理", -1, {
                    "uuid": doc.uuid,
                    "status": doc.status,
                }

            file_path = Path(doc.url)
            if not file_path.is_absolute():
                file_path = Path(str(doc.url).lstrip("/"))
            if not file_path.exists():
                self._merge_extra_data(doc, {
                    "processing_stage": "failed",
                    "failure_stage": "validate",
                    "failure_reason": "原始文件不存在，请重新上传",
                    "failed_at": datetime.now().isoformat(),
                })
                doc.status = 3
                await doc.save()
                return "原始文件不存在，请重新上传", -1, {
                    "uuid": doc.uuid,
                    "status": doc.status,
                }

            extra_data = getattr(doc, "extra_data", None) or {}
            retry_count = int(extra_data.get("retry_count") or 0) + 1
            task = self._build_processing_task(
                doc.uuid,
                file_path,
                doc.permission,
                extra_data.get("uploader_id"),
                extra_data.get("uploader_name"),
            )
            submit_success = document_processor.submit_task(task)
            if not submit_success:
                self._merge_extra_data(doc, {
                    "processing_stage": "failed",
                    "failure_stage": "submit",
                    "failure_reason": "重新处理提交失败，请稍后再试",
                    "failed_at": datetime.now().isoformat(),
                    "retry_count": retry_count,
                })
                doc.status = 3
                await doc.save()
                return "重新处理提交失败，请稍后再试", -1, {
                    "uuid": doc.uuid,
                    "status": doc.status,
                    "retry_count": retry_count,
                }

            self._merge_extra_data(doc, {
                "processing_stage": "queued",
                "queued_at": datetime.now().isoformat(),
                "retry_count": retry_count,
                "failure_stage": None,
                "failure_reason": None,
                "failed_at": None,
            })
            doc.status = 1
            await doc.save()
            return "已重新提交处理", 0, {
                "uuid": doc.uuid,
                "status": doc.status,
                "status_text": "处理中",
                "retry_count": retry_count,
                "processing_stage": "queued",
            }

        except Exception as e:
            logger.error(f"重新处理文档失败: {e}", exc_info=True)
            return "重新处理失败", -1, None

    async def _get_chunk_count_from_vector_store(self, document_uuid: str) -> int:
        """
        从向量库查询指定文档的 chunk 数量

        Args:
            document_uuid: 文档UUID

        Returns:
            int: chunk 数量
        """
        try:
            count = qdrant_client.count_by_document_uuid(
                document_uuid=document_uuid,
                collection_name=self.collection_name
            )
            if count > 0:
                return count
            return await ChunkModel.find(ChunkModel.document_uuid == document_uuid).count()

        except Exception as e:
            logger.warning(f"查询 chunk_count 失败: {e}")
            return await ChunkModel.find(ChunkModel.document_uuid == document_uuid).count()

    async def update_document_status(
        self,
        document_uuid: str,
        status: int,
        page: Optional[int] = None,
        content: Optional[str] = None
    ):
        """
        更新文档状态（异步版本，供 API 层使用）

        Args:
            document_uuid: 文档UUID
            status: 状态码（0.未处理，1.处理中，2.处理完成，3.处理失败）
            page: 文档页数（可选）
            content: 文档内容（可选）

        Returns:
            tuple: (message, ret) - message: 提示信息, ret: 返回码
        """
        try:
            # 1. 查询文档
            doc = await DocumentModel.find_one(DocumentModel.uuid == document_uuid)

            if not doc:
                return "文档不存在", -2

            # 2. 更新状态
            status_text_map = {
                0: "未处理",
                1: "处理中",
                2: "处理完成",
                3: "处理失败"
            }

            doc.status = status
            if page is not None:
                doc.page = page
            if content is not None:
                doc.content = content

            await doc.save()

            status_text = status_text_map.get(status, "未知")
            logger.info(f"文档状态已更新: {document_uuid} -> {status_text}")

            return f"状态更新成功: {status_text}", 0

        except Exception as e:
            logger.error(f"更新文档状态失败: {e}", exc_info=True)
            return f"更新失败: {str(e)}", -1

    def update_document_status_sync(
        self,
        document_uuid: str,
        status: int,
        page: Optional[int] = None,
        content: Optional[str] = None,
        extra_data_update: Optional[Dict[str, Any]] = None
    ):
        """
        更新文档状态（同步版本，供 Kafka 消费者使用）
        使用 pymongo 直接操作，避免事件循环冲突

        Args:
            document_uuid: 文档UUID
            status: 状态码（0.未处理，1.处理中，2.处理完成，3.处理失败）
            page: 文档页数（可选）
            content: 文档内容（可选）
            extra_data_update: 额外数据更新（可选，会合并到现有的extra_data中）

        Returns:
            tuple: (message, ret) - message: 提示信息, ret: 返回码
        """
        try:
            from pymongo import MongoClient
            from pkg.constants.constants import MONGODB_URL, MONGODB_DATABASE
            from datetime import datetime

            # 使用同步的 pymongo 客户端
            client = MongoClient(MONGODB_URL)
            db = client[MONGODB_DATABASE]
            collection = db['documents']

            # 查询文档
            doc = collection.find_one({"uuid": document_uuid})

            if not doc:
                client.close()
                return "文档不存在", -2

            # 准备更新数据
            update_data = {"status": status, "update_at": datetime.now()}
            if page is not None:
                update_data["page"] = page
            if content is not None:
                update_data["content"] = content

            # 🔥 更新 extra_data（合并新数据）
            if extra_data_update is not None:
                existing_extra_data = doc.get("extra_data", {})
                existing_extra_data.update(extra_data_update)
                update_data["extra_data"] = existing_extra_data

            # 更新文档
            result = collection.update_one(
                {"uuid": document_uuid},
                {"$set": update_data}
            )

            client.close()

            status_text_map = {
                0: "未处理",
                1: "处理中",
                2: "处理完成",
                3: "处理失败"
            }

            status_text = status_text_map.get(status, "未知")

            if result.modified_count > 0:
                logger.info(f"文档状态已更新（同步）: {document_uuid} -> {status_text}")
                return f"状态更新成功: {status_text}", 0
            else:
                logger.warning(f"文档状态未变化: {document_uuid} -> {status_text}")
                return f"文档状态未变化", 0

        except Exception as e:
            logger.error(f"更新文档状态失败（同步）: {e}", exc_info=True)
            return f"更新失败: {str(e)}", -1

    def _delete_from_vector_store(self, document_uuid: str) -> int:
        """
        从向量库删除指定文档的所有向量

        Args:
            document_uuid: 文档UUID

        Returns:
            int: 删除的向量数量
        """
        try:
            count = qdrant_client.count_by_document_uuid(
                document_uuid=document_uuid,
                collection_name=self.collection_name
            )
            qdrant_client.delete_by_document_uuid(
                document_uuid=document_uuid,
                collection_name=self.collection_name
            )
            return count

        except Exception as e:
            logger.error(f"删除文档向量失败: {e}", exc_info=True)
            return 0


# 导出单例
document_service = DocumentService()

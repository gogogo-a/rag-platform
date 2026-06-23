"""
消息客户端模块
支持 Channel（内存队列）和 Kafka（分布式队列）两种模式
"""
from internal.document_client.config_loader import config


def __getattr__(name):
    if name == "message_client":
        from internal.document_client.message_client import message_client
        return message_client
    if name == "document_processor":
        from internal.document_client.document_processor import document_processor
        return document_processor
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    'config',
    'message_client',
    'document_processor'
]

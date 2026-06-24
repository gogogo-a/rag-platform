from functools import wraps
from time import perf_counter

from beanie import Document
from beanie.odm.queries.delete import DeleteMany, DeleteOne
from beanie.odm.queries.find import FindMany, FindOne
from beanie.odm.queries.update import UpdateMany, UpdateOne

from pkg.utils.return_logger import log_database_return, record_database_duration


_INSTALLED = False


def _query_name(query) -> str:
    model = getattr(query, "document_model", None)
    model_name = getattr(model, "__name__", "MongoDB")
    return f"{model_name}.{query.__class__.__name__}"


def _wrap_awaitable_method(cls, method_name: str):
    original = getattr(cls, method_name)
    if getattr(original, "_return_logger_wrapped", False):
        return

    @wraps(original)
    def wrapped(self, *args, **kwargs):
        start = perf_counter()
        result = yield from original(self, *args, **kwargs)
        record_database_duration((perf_counter() - start) * 1000)
        log_database_return(f"{_query_name(self)}.{method_name}", result)
        return result

    wrapped._return_logger_wrapped = True
    setattr(cls, method_name, wrapped)


def _wrap_async_method(cls, method_name: str):
    original = getattr(cls, method_name)
    if getattr(original, "_return_logger_wrapped", False):
        return

    @wraps(original)
    async def wrapped(self, *args, **kwargs):
        start = perf_counter()
        result = await original(self, *args, **kwargs)
        record_database_duration((perf_counter() - start) * 1000)
        log_database_return(f"{_query_name(self)}.{method_name}", result)
        return result

    wrapped._return_logger_wrapped = True
    setattr(cls, method_name, wrapped)


def _wrap_document_method(method_name: str):
    original = getattr(Document, method_name)
    if getattr(original, "_return_logger_wrapped", False):
        return

    @wraps(original)
    async def wrapped(self, *args, **kwargs):
        start = perf_counter()
        result = await original(self, *args, **kwargs)
        record_database_duration((perf_counter() - start) * 1000)
        log_database_return(f"{self.__class__.__name__}.{method_name}", result)
        return result

    wrapped._return_logger_wrapped = True
    setattr(Document, method_name, wrapped)


def install_database_return_logger() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    _wrap_awaitable_method(FindOne, "__await__")
    _wrap_async_method(FindMany, "to_list")
    _wrap_async_method(FindMany, "count")
    _wrap_async_method(FindOne, "count")

    _wrap_awaitable_method(UpdateOne, "__await__")
    _wrap_awaitable_method(UpdateMany, "__await__")
    _wrap_awaitable_method(DeleteOne, "__await__")
    _wrap_awaitable_method(DeleteMany, "__await__")

    for method_name in ("insert", "save", "replace", "delete"):
        _wrap_document_method(method_name)

    _INSTALLED = True

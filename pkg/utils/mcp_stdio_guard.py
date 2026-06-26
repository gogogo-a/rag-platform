"""Helpers for MCP subprocess startup."""
import os
import sys
from contextlib import contextmanager


@contextmanager
def redirected_stdout():
    original_stdout = sys.stdout
    if os.getenv("PLANTFORM_MCP_STDIO") == "1":
        sys.stdout = sys.stderr
    try:
        yield
    finally:
        sys.stdout = original_stdout

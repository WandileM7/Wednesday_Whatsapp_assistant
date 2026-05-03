from __future__ import annotations
from typing import Any, Awaitable, Callable, TypedDict

ToolFn = Callable[..., Awaitable[Any]]
class ToolSpec(TypedDict):
    description: str; schema: dict; fn: ToolFn

REGISTRY: dict[str, ToolSpec] = {}

def register(name, description, schema):
    def decorator(fn):
        REGISTRY[name] = {"description": description, "schema": schema, "fn": fn}
        return fn
    return decorator

from . import builtin, google, spotify  # noqa
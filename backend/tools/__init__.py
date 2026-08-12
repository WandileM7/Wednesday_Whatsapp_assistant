from __future__ import annotations
from contextvars import ContextVar
from typing import Any, Awaitable, Callable, TypedDict

# Which user the agent is currently serving; set per turn so tools like
# search_conversations can scope to the right history.
CURRENT_USER: ContextVar[str] = ContextVar("CURRENT_USER", default="")

ToolFn = Callable[..., Awaitable[Any]]
class ToolSpec(TypedDict):
    description: str; schema: dict; fn: ToolFn

REGISTRY: dict[str, ToolSpec] = {}

def register(name, description, schema):
    def decorator(fn):
        REGISTRY[name] = {"description": description, "schema": schema, "fn": fn}
        return fn
    return decorator

from . import browser, builtin, google, spotify  # noqa
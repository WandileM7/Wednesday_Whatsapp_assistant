"""browse_web: drive a real browser for tasks a fetch can't do.

`fetch_page` handles static pages and is far cheaper, so this tool is scoped
to the cases it can't touch — clicking through a flow, filling a form, paging
through results, anything behind JavaScript. browser-use runs the loop; the
local Ollama model does the thinking, so the zero-bill promise holds.

Opt-in (ENABLE_BROWSER_USE) because it wants Chromium on disk and a capable
model: an 8B model will fumble long browsing chains. It's also gated behind
the approval prompt by default — a browser acting with your cookies is a
consequential thing to hand an agent.
"""
from __future__ import annotations
import asyncio, logging

from . import register
from ..config import settings

log = logging.getLogger(__name__)


def _llm():
    """browser-use's LLM wrapper, across the versions that moved it around."""
    model = settings.browser_model or settings.ollama_model
    host = settings.ollama_host
    try:
        from browser_use import ChatOllama                    # >= 0.2
    except ImportError:
        try:
            from browser_use.llm import ChatOllama            # 0.1.x
        except ImportError:
            from langchain_ollama import ChatOllama           # older still
            return ChatOllama(model=model, base_url=host)
    try:
        return ChatOllama(model=model, host=host)
    except TypeError:                                          # param renamed
        return ChatOllama(model=model, base_url=host)


_DESCRIPTION = (
    "Drive a real browser to complete a task on the web: click through pages, fill "
    "forms, work past JavaScript. Slow and heavyweight — prefer web_search and "
    "fetch_page, and use this only when a page must actually be interacted with.")
_SCHEMA = {"type":"object","properties":{
    "task":{"type":"string","description":"What to accomplish, in plain English"},
    "start_url":{"type":"string","description":"Page to start from, if known"},
    "max_steps":{"type":"integer","default":12,"minimum":1,"maximum":30}},
    "required":["task"]}


async def browse_web(task: str, start_url: str = "", max_steps: int = 12):
    if not settings.enable_browser_use:
        return "Browser use is disabled. Set ENABLE_BROWSER_USE=true to allow it."
    try:
        from browser_use import Agent
    except ImportError:
        return ("browser-use isn't installed. Install it with: pip install browser-use "
                "&& playwright install chromium")
    if start_url:
        task = f"Start at {start_url}. {task}"
    try:
        agent = Agent(task=task, llm=_llm())
    except Exception as exc:                    # noqa: BLE001 — config problems land here
        log.exception("browser-use setup failed")
        return f"Could not start the browser agent: {exc}"
    try:
        history = await asyncio.wait_for(agent.run(max_steps=max_steps),
                                         timeout=settings.browser_timeout)
    except asyncio.TimeoutError:
        return f"Gave up after {settings.browser_timeout:.0f}s of browsing."
    except Exception as exc:                    # noqa: BLE001 — the model reads this
        log.exception("browse_web failed")
        return f"Browsing failed: {exc}"
    finally:
        # Leaked Chromium processes are how a long-running assistant runs a
        # laptop out of RAM; close on every path, including the timeout.
        for closer in ("close", "stop"):
            if fn := getattr(agent, closer, None):
                try:
                    result = fn()
                    if asyncio.iscoroutine(result):
                        await result
                    break
                except Exception:               # noqa: BLE001
                    log.debug("browser cleanup via %s() failed", closer, exc_info=True)
    return _result_text(history)


def _result_text(history) -> str:
    """Pull the final answer out of an AgentHistoryList, whatever shape it is."""
    for attr in ("final_result", "extracted_content"):
        fn = getattr(history, attr, None)
        if callable(fn):
            try:
                if text := fn():
                    text = text if isinstance(text, str) else str(text)
                    return text[:4000] + ("\n[truncated]" if len(text) > 4000 else "")
            except Exception:                   # noqa: BLE001
                log.debug("could not read %s from browse result", attr, exc_info=True)
    text = str(history)
    return text[:2000] + ("\n[truncated]" if len(text) > 2000 else "")


# Registered always, advertised only when enabled — agent._disabled() decides.
# An unusable tool's schema would otherwise ride in every prompt, and the
# context window is the scarce resource here; but staying registered means a
# call that arrives anyway gets the reason back instead of "no such tool".
register("browse_web", _DESCRIPTION, _SCHEMA)(browse_web)

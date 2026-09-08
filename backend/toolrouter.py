"""Which tools to put in front of the model for this turn.

All 26 schemas came to 2438 tokens and went into every prompt, so a question
about the weather carried the full argument spec for spotify_queue. Two costs,
and the second is the one that matters:

  - 2438 tokens of a 8192-token window, on a box that evaluates prompt at 3-4
    tokens/sec.
  - Tool-selection accuracy on a 7B model falls off with the number of options
    on offer. agent.py already documents adherence going 20/20 -> 8/20 as
    *history* grew; schema count pulls the same lever.

So: a small always-on core, plus the groups this turn actually implicates.

Two rules keep the routing from being worse than the bloat it replaces:

  - Anything not explicitly grouped is core. A tool added later, or an MCP tool
    that appears at runtime, is always offered rather than silently routed away.
  - Groups are sticky. "skip it" and "next one" carry no keyword at all, so a
    group stays available for a few turns after it is used — otherwise the
    follow-up to a song request finds no music tools and she talks about the
    song instead of skipping it.

Over-matching is cheap here and under-matching is not, so the patterns lean
broad on purpose.
"""
from __future__ import annotations
import re

from .tools import REGISTRY

# Always offered: cheap, general, or needed to answer "what can you do".
CORE = {
    "get_time", "get_weather", "system_status",
    "search_conversations", "set_reply_mode",
}

# group -> (tool names, trigger pattern)
_GROUPS: dict[str, tuple[set[str], re.Pattern]] = {
    "music": (
        {"spotify_play", "spotify_search", "spotify_queue",
         "spotify_now_playing", "spotify_playlist", "spotify_library",
         "spotify_control"},
        re.compile(r"\b(play|pause|resume|stop|skip|next|previous|song|track|"
                   r"album|artist|playlist|spotify|music|tune|volume|queue|"
                   r"shuffle|listen|put on|now playing|vibe)\b", re.I),
    ),
    "mail": (
        {"gmail_search", "gmail_send", "gmail_create_draft", "gmail_get_thread"},
        re.compile(r"\b(mail|email|e-mail|gmail|inbox|unread|draft|cc|bcc|"
                   r"subject|reply to|forward|sender|newsletter)\b", re.I),
    ),
    "calendar": (
        {"calendar_list_events", "calendar_create_event",
         "calendar_update_event", "calendar_delete_event"},
        re.compile(r"\b(calendar|diary|meeting|appointment|schedule|event|"
                   r"invite|booking|free|busy|agenda)\b", re.I),
    ),
    "tasks": (
        {"tasks_add", "tasks_list"},
        re.compile(r"\b(task|tasks|todo|to-do|to do|checklist|backlog)\b", re.I),
    ),
    "reminders": (
        {"set_reminder", "cancel_reminder", "list_reminders"},
        re.compile(r"\b(remind|reminder|reminders|alarm|nudge|ping me|"
                   r"wake me|forget)\b", re.I),
    ),
    "web": (
        {"web_search", "fetch_page"},
        re.compile(r"\b(search|google|look up|lookup|news|article|website|"
                   r"web|online|link|url|latest|headline|who is|what is|"
                   r"how much|price)\b", re.I),
    ),
    "vision": (
        {"see_image", "look"},
        re.compile(r"\b(image|photo|picture|screenshot|camera|look at|"
                   r"see this|what.s this|holding|reading|wearing)\b", re.I),
    ),
    "skills": (
        {"use_skill", "propose_skill"},
        re.compile(r"\b(skill|skills|routine|workflow|procedure)\b", re.I),
    ),
    "briefing": (
        {"set_daily_briefing", "cancel_daily_briefing"},
        re.compile(r"\b(briefing|brief me|morning report|daily (?:report|rundown|"
                   r"summary)|every morning|each morning)\b", re.I),
    ),
    "news": (
        {"news_digest"},
        re.compile(r"\b(news|headline|headlines|current events|what.s happening|"
                   r"going on in the world)\b", re.I),
    ),
    "convert": (
        {"convert_units", "convert_currency", "world_time"},
        re.compile(r"\b(convert|conversion|how many|how much is|in (?:celsius|"
                   r"fahrenheit|kg|lbs|pounds|miles|km|metres|meters|feet)|"
                   r"exchange rate|currency|dollars?|euros?|rands?|pounds?|"
                   r"time in|timezone|time zone)\b", re.I),
    ),
    "people": (
        {"remember_person", "recall_person", "list_people", "forget_person"},
        re.compile(r"\b(who is|who.s|remember that|note that|colleague|friend|"
                   r"my (?:boss|manager|brother|sister|mum|mom|dad|partner|wife|"
                   r"husband)|people|contacts?)\b", re.I),
    ),
    "docs": (
        {"search_documents"},
        re.compile(r"\b(document|documents|notes?|my files?|wrote down|"
                   r"in my notes)\b", re.I),
    ),
    "home": (
        {"home_control", "home_list_devices", "home_get_state",
         "home_set_light", "home_set_temperature", "home_activate_scene"},
        re.compile(r"\b(lights?|lamp|thermostat|heating|aircon|air con|"
                   r"temperature in|switch (?:on|off)|turn (?:on|off)|scene|"
                   r"home assistant|smart home|blinds?|curtains?)\b", re.I),
    ),
}

# How many trailing messages count as "recently used" for stickiness.
_STICKY_MESSAGES = 12


def _grouped() -> set[str]:
    return {name for tools, _ in _GROUPS.values() for name in tools}


def _group_of(tool: str) -> str | None:
    for group, (tools, _) in _GROUPS.items():
        if tool in tools:
            return group
    return None


def _recent_groups(convo: list[dict]) -> set[str]:
    """Groups touched in the recent tail, so follow-ups keep their tools."""
    out: set[str] = set()
    for m in convo[-_STICKY_MESSAGES:]:
        names = [m["name"]] if m.get("role") == "tool" and m.get("name") else []
        names += [c.get("function", {}).get("name", "")
                  for c in (m.get("tool_calls") or [])]
        for name in names:
            if group := _group_of(name):
                out.add(group)
    return out


def groups(user_text: str) -> set[str]:
    """Intent groups this text implicates.

    Public because turncost needs to ask "will this turn call a tool" — a tool
    call means a second model round over a bigger prompt, which is most of what
    makes a turn expensive. It asks here rather than keeping a second copy of
    the patterns, which would drift the moment either side gained a group.
    """
    return {g for g, (_, pattern) in _GROUPS.items() if pattern.search(user_text or "")}


def select(user_text: str, convo: list[dict] | None = None) -> set[str]:
    """Tool names to offer this turn."""
    registered = set(REGISTRY)
    # Ungrouped tools (including anything registered later, and MCP tools) ride
    # along with core rather than being routed away by omission.
    allowed = (CORE | (registered - _grouped())) & registered

    active = groups(user_text)
    active |= _recent_groups(convo or [])
    for group in active:
        allowed |= _GROUPS[group][0] & registered
    return allowed

"""One OpenAI-compatible chat client with tool calling, for every provider:

* local `mlx_lm.server` (Apple silicon), * vLLM on Modal, * Fireworks, * Azure OpenAI (optional).

Retries with exponential backoff on rate limits, timeouts and server errors; a simple request-rate
limiter; temperature 0 and one sample per prompt (pre-registered). Tool calls are read from the
structured `tool_calls` field when the server parses them, and otherwise from the text (Jais 3
<ifm|tool_call> blocks, Hermes/Qwen <tool_call> blocks, Llama 3 JSON), so servers without a tool parser
(mlx_lm.server for Jais 3, prompted-tool models) work the same way.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import re
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import openai

from .models import ModelSpec
from .parse import _THINK_CLOSE, strip_reasoning
from .prompts import prompted_tool_text

RETRY_STATUS = {408, 409, 425, 429, 500, 502, 503, 504, 520, 522, 524}


def load_env(path: Path | None = None) -> None:
    """Read KEY=VALUE lines from bench_llm/.env into os.environ (existing variables win)."""
    path = path or Path(__file__).resolve().parents[2] / ".env"
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip().strip('"').strip("'")
        os.environ.setdefault(k.strip(), v)


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: Any          # dict when parseable, else the raw string


@dataclass
class ChatResult:
    content: str            # answer text with reasoning removed
    raw_content: str        # text as returned
    reasoning: str
    tool_calls: list[ToolCall]
    finish_reason: str | None
    usage: dict[str, int]
    latency_s: float
    tool_calls_from_text: bool = False
    truncated_in_reasoning: bool = False


# ------------------------------------------------------ text tool calls ---
_DEC = json.JSONDecoder()


def _json_objects(s: str) -> list[dict]:
    out, i = [], 0
    while True:
        j = s.find("{", i)
        if j < 0:
            return out
        try:
            obj, end = _DEC.raw_decode(s, j)
        except json.JSONDecodeError:
            i = j + 1
            continue
        if isinstance(obj, dict):
            out.append(obj)
        i = end


def _coerce(v: str) -> Any:
    v = v.strip()
    try:
        return json.loads(v)
    except json.JSONDecodeError:
        return v


def parse_text_tool_calls(text: str, tool_names: set[str] | None = None) -> list[ToolCall]:
    """Find tool calls written as text by the model."""
    calls: list[ToolCall] = []
    if not text:
        return calls

    def ok(name: Any) -> bool:
        return isinstance(name, str) and (tool_names is None or name in tool_names)

    # Jais 3 native format: json or xml variants
    for m in re.finditer(r"<ifm\|tool_call>(.*?)</ifm\|tool_call>", text, re.S):
        body = m.group(1).strip()
        if body.startswith("{"):
            objs = _json_objects(body)
            if objs and ok(objs[0].get("name")):
                calls.append(ToolCall(f"call_{uuid.uuid4().hex[:12]}", objs[0]["name"],
                                      objs[0].get("arguments", objs[0].get("parameters", {}))))
            continue
        name = body.split("<ifm|", 1)[0].strip()
        args: dict[str, Any] = {}
        for k, v in re.findall(r"<ifm\|arg_key>(.*?)</ifm\|arg_key>\s*(?:<ifm\|arg_type>.*?</ifm\|arg_type>\s*)?"
                               r"<ifm\|arg_value>(.*?)</ifm\|arg_value>", body, re.S):
            args[k.strip()] = _coerce(v)
        if ok(name):
            calls.append(ToolCall(f"call_{uuid.uuid4().hex[:12]}", name, args))
    if calls:
        return calls
    # Hermes / Qwen / prompted format
    for m in re.finditer(r"<tool_call>(.*?)(?:</tool_call>|$)", text, re.S):
        for obj in _json_objects(m.group(1))[:1]:
            if ok(obj.get("name")):
                calls.append(ToolCall(f"call_{uuid.uuid4().hex[:12]}", obj["name"],
                                      obj.get("arguments", obj.get("parameters", {}))))
    if calls:
        return calls
    # Llama 3 JSON ({"name": ..., "parameters": ...}), possibly after <|python_tag|> or in a code fence
    for obj in _json_objects(text):
        if ok(obj.get("name")) and isinstance(obj.get("arguments", obj.get("parameters")), (dict, str)):
            calls.append(ToolCall(f"call_{uuid.uuid4().hex[:12]}", obj["name"],
                                  obj.get("arguments", obj.get("parameters"))))
    return calls


def _args_obj(a: Any) -> Any:
    if isinstance(a, str):
        try:
            return json.loads(a)
        except json.JSONDecodeError:
            return a
    return a


# ---------------------------------------------------------------- client ---
class RateLimiter:
    def __init__(self, rpm: int | None):
        self.interval = 60.0 / rpm if rpm else 0.0
        self._lock = asyncio.Lock()
        self._next = 0.0

    async def wait(self) -> None:
        if not self.interval:
            return
        async with self._lock:
            now = time.monotonic()
            if now < self._next:
                await asyncio.sleep(self._next - now)
            self._next = max(now, self._next) + self.interval


class ChatClient:
    def __init__(self, spec: ModelSpec, *, base_url: str | None = None, api_key: str | None = None,
                 http_client: httpx.AsyncClient | None = None, max_attempts: int = 6, backoff_s: float = 2.0):
        self.spec = spec
        self.max_attempts = max_attempts
        self.backoff_s = backoff_s
        self.limiter = RateLimiter(spec.rpm)
        key = api_key if api_key is not None else spec.api_key()
        if spec.provider == "azure":
            self.client: Any = openai.AsyncAzureOpenAI(
                azure_endpoint=base_url or spec.resolved_base_url(), api_key=key,
                api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21"),
                max_retries=0, timeout=spec.timeout_s, http_client=http_client)
        else:
            self.client = openai.AsyncOpenAI(base_url=base_url or spec.resolved_base_url(), api_key=key,
                                             max_retries=0, timeout=spec.timeout_s, http_client=http_client)

    # ---- message shapes for multi-turn tool use ----------------------
    def prepare(self, messages: list[dict], tools: list[dict] | None) -> tuple[list[dict], list[dict] | None]:
        if tools and self.spec.tool_mode == "prompted":
            msgs = [dict(m) for m in messages]
            msgs[0]["content"] = msgs[0]["content"] + prompted_tool_text(tools)
            return msgs, None
        return messages, tools

    def assistant_message(self, res: ChatResult) -> dict:
        if self.spec.tool_mode == "prompted" or not res.tool_calls:
            return {"role": "assistant", "content": res.raw_content if self.spec.tool_mode == "prompted" else res.content}
        msg: dict = {
            "role": "assistant",
            "content": res.content or "",
            "tool_calls": [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.name,
                              "arguments": (_args_obj(tc.arguments) if self.spec.tool_args_as_dict
                                            else (tc.arguments if isinstance(tc.arguments, str)
                                                  else json.dumps(tc.arguments, ensure_ascii=False)))}}
                for tc in res.tool_calls
            ],
        }
        if self.spec.reasoning and self.spec.provider == "vllm":
            # Reasoning templates (Jais 3) require the model's own reasoning on an assistant turn that is sent
            # back with tool calls; vLLM passes this field through to the chat template.
            msg["reasoning_content"] = res.reasoning or ""
        return msg

    def tool_message(self, tc: ToolCall, result: dict) -> dict:
        body = json.dumps(result, ensure_ascii=False)
        if self.spec.tool_mode == "prompted":
            return {"role": "user", "content": f"<tool_response>\n{body}\n</tool_response>"}
        return {"role": "tool", "tool_call_id": tc.id, "content": body}

    # ---- request ------------------------------------------------------
    async def _create(self, req: dict) -> Any:
        last: Exception | None = None
        for attempt in range(self.max_attempts):
            await self.limiter.wait()
            try:
                return await self.client.chat.completions.create(**req)
            except (openai.RateLimitError, openai.APITimeoutError, openai.APIConnectionError,
                    openai.InternalServerError) as e:
                last = e
            except openai.APIStatusError as e:
                if e.status_code not in RETRY_STATUS:
                    raise
                last = e
            if attempt + 1 < self.max_attempts:
                await asyncio.sleep(min(60.0, self.backoff_s * 2 ** attempt) * (0.5 + random.random()))
        assert last is not None
        raise last

    async def chat(self, messages: list[dict], tools: list[dict] | None = None) -> ChatResult:
        msgs, native_tools = self.prepare(messages, tools)
        req: dict[str, Any] = {"model": self.spec.model_id, "messages": msgs, "temperature": self.spec.temperature,
                               "max_tokens": self.spec.max_tokens}
        if native_tools:
            req["tools"] = native_tools
            req["tool_choice"] = "auto"
        if self.spec.extra_body:
            req["extra_body"] = self.spec.extra_body
        t0 = time.perf_counter()
        resp = await self._create(req)
        dt = time.perf_counter() - t0
        choice = resp.choices[0]
        msg = choice.message
        raw = msg.content or ""
        extra = getattr(msg, "model_extra", None) or {}
        reasoning = (getattr(msg, "reasoning_content", None) or extra.get("reasoning_content")
                     or extra.get("reasoning") or "")
        content, think = strip_reasoning(raw)
        reasoning = (reasoning + ("\n" if reasoning and think else "") + think) if think else reasoning
        truncated = False
        if (self.spec.reasoning and not reasoning and choice.finish_reason == "length"
                and not _THINK_CLOSE.search(raw)):
            # The chat template opened the thinking block in the prompt (Jais 3, K2-Think) and the output was
            # cut off before the block closed: everything returned is reasoning, there is no answer.
            reasoning, content, truncated = raw, "", True
        names = {t["function"]["name"] for t in (tools or [])}
        calls = [ToolCall(tc.id or f"call_{uuid.uuid4().hex[:12]}", tc.function.name, _args_obj(tc.function.arguments))
                 for tc in (msg.tool_calls or [])]
        from_text = False
        if not calls and tools:
            calls = parse_text_tool_calls(content, names) or parse_text_tool_calls(raw, names)
            from_text = bool(calls)
        usage = {}
        if resp.usage is not None:
            usage = {"prompt_tokens": resp.usage.prompt_tokens or 0, "completion_tokens": resp.usage.completion_tokens or 0}
        return ChatResult(content=content, raw_content=raw, reasoning=reasoning, tool_calls=calls,
                          finish_reason=choice.finish_reason, usage=usage, latency_s=dt, tool_calls_from_text=from_text,
                          truncated_in_reasoning=truncated)

    async def aclose(self) -> None:
        await self.client.close()


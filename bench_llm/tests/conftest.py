"""Shared fixtures: a fake OpenAI-compatible server (httpx.MockTransport). No network, no paid calls."""

from __future__ import annotations

import json
from typing import Callable

import httpx
import pytest

from silsila_bench import models
from silsila_bench.clients import ChatClient


def completion(content: str | None = "", tool_calls: list | None = None, finish: str = "stop",
               reasoning: str | None = None) -> dict:
    msg: dict = {"role": "assistant", "content": content}
    if tool_calls:
        msg["tool_calls"] = [
            {"id": f"call_{i}", "type": "function",
             "function": {"name": n, "arguments": a if isinstance(a, str) else json.dumps(a, ensure_ascii=False)}}
            for i, (n, a) in enumerate(tool_calls)
        ]
        finish = "tool_calls"
    if reasoning is not None:
        msg["reasoning_content"] = reasoning
    return {"id": "x", "object": "chat.completion", "created": 0, "model": "m",
            "choices": [{"index": 0, "message": msg, "finish_reason": finish}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}


class FakeServer:
    """Calls `handler(request_json, call_index)` -> (status, body)."""

    def __init__(self, handler: Callable[[dict, int], tuple[int, dict]]):
        self.handler = handler
        self.requests: list[dict] = []

    def transport(self) -> httpx.MockTransport:
        def h(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            self.requests.append(body)
            status, out = self.handler(body, len(self.requests) - 1)
            return httpx.Response(status, json=out)
        return httpx.MockTransport(h)

    def client(self, model: str = "gpt-oss-120b", **spec_overrides) -> ChatClient:
        import dataclasses
        spec = dataclasses.replace(models.get(model), **spec_overrides)
        return ChatClient(spec, base_url="http://fake/v1", api_key="test",
                          http_client=httpx.AsyncClient(transport=self.transport()), backoff_s=0.0)


@pytest.fixture
def fake_server():
    return FakeServer

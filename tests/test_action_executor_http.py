import httpx
import pytest

import actions
from actions import ActionExecutor, RuntimeContext


class DummyLogger:
    def info(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass


class DummyRegistry:
    def get(self, *_args, **_kwargs):
        return None


@pytest.mark.asyncio
async def test_execute_http_preview_uses_placeholders(monkeypatch):
    monkeypatch.setattr(actions, "jmespath", None)
    monkeypatch.setattr(actions, "jsonpath_parse", None)

    called_types = []
    original_aapply = ActionExecutor._aapply_extractor

    async def tracking_aapply(self, extractor_type, expression, response):
        called_types.append(extractor_type)
        return await original_aapply(self, extractor_type, expression, response)

    monkeypatch.setattr(ActionExecutor, "_aapply_extractor", tracking_aapply)

    logger = DummyLogger()
    executor = ActionExecutor(
        logger=logger, registry=DummyRegistry(), modular_registry=DummyRegistry()
    )

    async def fake_get_http_client():
        raise AssertionError("HTTP client should not be used during preview")

    monkeypatch.setattr(executor, "_get_http_client", fake_get_http_client)

    action = {
        "config": {
            "request": {
                "method": "POST",
                "url": "https://example.com/{{ runtime.chat_id }}/preview",
                "headers": {"X-Token": "{{ runtime.variables.sample }}"},
                "body": {
                    "mode": "json",
                    "json": {"echo": "{{ variables.sample }}"},
                },
            },
            "parse": {
                "extractor": {"type": "jmespath", "expression": "payload.value"},
                "variables": [
                    {
                        "name": "from_jmespath",
                        "type": "jmespath",
                        "expression": "payload.value",
                    },
                    {
                        "name": "from_jsonpath",
                        "type": "jsonpath",
                        "expression": "$.payload.value",
                    },
                    {
                        "name": "from_template",
                        "type": "template",
                        "template": "{{ response.status_code }}",
                    },
                    {
                        "name": "runtime_val",
                        "type": "runtime",
                        "key": "sample",
                    },
                ],
            },
            "render": {
                "template": (
                    "Extracted={{ extracted }}, Vars={{ variables.from_jmespath }}|"
                    "{{ variables.from_jsonpath }}|{{ variables.from_template }}|"
                    "{{ variables.runtime_val }}"
                )
            },
        }
    }

    runtime = RuntimeContext(chat_id="chat-1", variables={"sample": "VALUE"})

    result = await executor._execute_http(
        action,
        button={"id": "btn"},
        menu={"id": "menu"},
        runtime=runtime,
        preview=True,
    )

    assert result.success is True
    assert result.data["response_status"] == 200
    assert result.data["extracted"] == "<preview:extracted.jmespath>"
    assert (
        result.data["variables"]["from_jmespath"]
        == "<preview:variables.from_jmespath>"
    )
    assert (
        result.data["variables"]["from_jsonpath"]
        == "<preview:variables.from_jsonpath>"
    )
    assert result.data["variables"]["from_template"] == "200"
    assert result.data["variables"]["runtime_val"] == "VALUE"
    assert "<preview:variables.from_jmespath>" in (result.new_text or "")
    assert "<preview:variables.from_jsonpath>" in (result.new_text or "")
    assert "200" in (result.new_text or "")
    assert "VALUE" in (result.new_text or "")
    assert "jmespath" not in called_types
    assert "jsonpath" not in called_types

    await executor.close()


@pytest.mark.asyncio
async def test_execute_http_network_failure(monkeypatch):
    logger = DummyLogger()
    executor = ActionExecutor(
        logger=logger, registry=DummyRegistry(), modular_registry=DummyRegistry()
    )

    class FailingClient:
        async def request(self, **kwargs):
            raise httpx.ConnectError(
                "boom",
                request=httpx.Request(kwargs["method"], kwargs["url"]),
            )

    async def fake_get_http_client():
        return FailingClient()

    monkeypatch.setattr(executor, "_get_http_client", fake_get_http_client)

    action = {
        "config": {
            "request": {
                "method": "GET",
                "url": "https://example.com/fail",
            }
        }
    }

    runtime = RuntimeContext(chat_id="chat-fail")

    result = await executor._execute_http(
        action,
        button={"id": "btn"},
        menu={"id": "menu"},
        runtime=runtime,
        preview=False,
    )

    assert result.success is False
    assert result.error is not None
    assert "HTTP 请求失败" in result.error
    assert "GET https://example.com/fail" in result.error
    assert "boom" in result.error

    await executor.close()

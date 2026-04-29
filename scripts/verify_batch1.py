import asyncio
import base64
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.auth import _b64url_decode
from core.claude_compat import ToolifyParser
from core.tabbit_client import TabbitClient
import routes.openai_compat as openai_compat


def _make_jwt(payload: dict) -> str:
    header = {"alg": "none", "typ": "JWT"}
    h = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
    p = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"{h}.{p}.x"


def test_jwt_padding():
    for payload in [{"sub": "u1"}, {"id": "u2"}, {"id": "user-123", "sub": "u3"}]:
        token = _make_jwt(payload)
        client = TabbitClient(token)
        expected = payload.get("id", payload.get("sub"))
        assert client.user_id == expected, (client.user_id, expected)


def test_parser_flush_threshold():
    p = ToolifyParser(trigger_signal=None, thinking_enabled=False)
    p.feed_text("a" * 127)
    assert p.consume_events() == []
    p.feed_text("a")
    ev = p.consume_events()
    assert ev and ev[0]["type"] == "text" and len(ev[0]["content"]) == 128


def test_auth_b64url_padding():
    """含「无 padding 段长度已是 4 倍数」时也必须正确解码（旧实现会多补 '='）。"""
    for raw in (b"{}", b"x" * 7, b"y" * 22, b'{"role":"admin","exp":9999999999}'):
        enc = base64.urlsafe_b64encode(raw).decode().rstrip("=")
        assert _b64url_decode(enc) == raw


def test_multi_invoke_same_buffer():
    sig = "<<CALL_tool>>"
    p = ToolifyParser(trigger_signal=sig, thinking_enabled=False)
    blob = (
        f"{sig}\n"
        r'<invoke name="tool_a"><parameter name="k">"v"</parameter></invoke>'
        f"{sig}\n"
        r'<invoke name="tool_b"><parameter name="x">1</parameter></invoke>'
    )
    p.feed_text(blob)
    p.finish()
    ev = [e for e in p.consume_events() if e["type"] != "end"]
    tools = [e for e in ev if e["type"] == "tool_call"]
    assert len(tools) == 2, [e["type"] for e in ev]
    assert tools[0]["call"]["name"] == "tool_a"
    assert tools[1]["call"]["name"] == "tool_b"


def test_thinking_close_no_lag():
    p = ToolifyParser(trigger_signal="<<CALL_abc123>>", thinking_enabled=True)
    p.feed_text("<thinking>abc</thinking>X")
    p.finish()
    ev = p.consume_events()
    types = [e["type"] for e in ev]
    assert "thinking" in types
    assert any(e["type"] == "text" and "X" in e["content"] for e in ev)


async def test_stream_handler_error():
    class DummyClient:
        async def send_message(self, *args, **kwargs):
            yield {"event": "error", "data": {"message": "simulated upstream fail"}}

    class TM:
        async def report_success(self, *args, **kwargs):
            pass

        async def report_error(self, *args, **kwargs):
            pass

    class Logs:
        def add(self, *args, **kwargs):
            pass

    openai_compat._tm = TM()
    openai_compat._logs = Logs()

    chunks = []
    async for c in openai_compat._stream_handler(
        DummyClient(), "sid", "content", "最佳", "best", "cid", "token", "tid"
    ):
        chunks.append(c)

    joined = "\n".join(chunks)
    assert '"object": "error"' in joined or '"object":"error"' in joined
    assert "[DONE]" in joined


async def test_stream_handler_connection_error():
    """网络类异常：应输出 error 帧 + [DONE]，而非裸截断。"""

    class DiscClient:
        async def send_message(self, *args, **kwargs):
            raise OSError("connection reset")
            yield {"event": "message_chunk", "data": {}}  # noqa: unreachable — 需 async generator 语法

    class TM:
        async def report_success(self, *args, **kwargs):
            pass

        async def report_error(self, *args, **kwargs):
            pass

    class Logs:
        def add(self, *args, **kwargs):
            pass

    openai_compat._tm = TM()
    openai_compat._logs = Logs()
    chunks = []
    async for c in openai_compat._stream_handler(
        DiscClient(), "sid", "content", "最佳", "best", "cid", "n", "tid"
    ):
        chunks.append(c)
    joined = "\n".join(chunks)
    assert "stream_exception" in joined
    assert "[DONE]" in joined


async def main():
    test_jwt_padding()
    test_auth_b64url_padding()
    test_parser_flush_threshold()
    test_multi_invoke_same_buffer()
    test_thinking_close_no_lag()
    await test_stream_handler_error()
    await test_stream_handler_connection_error()
    print("verify_batch1: PASS")


if __name__ == "__main__":
    asyncio.run(main())

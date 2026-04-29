import asyncio
import base64
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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


async def main():
    test_jwt_padding()
    test_parser_flush_threshold()
    test_thinking_close_no_lag()
    await test_stream_handler_error()
    print("verify_batch1: PASS")


if __name__ == "__main__":
    asyncio.run(main())

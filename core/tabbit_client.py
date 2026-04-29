import html
import re
import json
import uuid
import hashlib
import base64
import urllib.parse
import time
import secrets
from typing import AsyncGenerator

import httpx

MODEL_MAP = {
    "best": "最佳",
    "gpt-5.5": "GPT-5.5",
    "gpt-5.4": "GPT-5.4",
    "gpt-5.2-chat": "GPT-5.2-Chat",
    "gpt-5.1-chat": "GPT-5.1-Chat",
    "deepseek-v4-pro": "DeepSeek-V4-Pro",
    "deepseek-v4-flash": "DeepSeek-V4-Flash",
    "gemini-3.1-pro": "Gemini-3.1-Pro",
    "gemini-3-flash": "Gemini-3-Flash",
    "gemini-2.5-flash": "Gemini-2.5-Flash",
    "claude-opus-4.7": "Claude-Opus-4.7",
    "claude-sonnet-4.6": "Claude-Sonnet-4.6",
    "claude-haiku-4.5": "Claude-Haiku-4.5",
    "kimi-k2.6": "Kimi-K2.6",
    "glm-5.1": "GLM-5.1",
    "glm-5v-turbo": "GLM-5V-Turbo",
    "glm-5": "GLM-5",
    "deepseek-v3.2": "DeepSeek-V3.2",
    "minimax-m2.5": "MiniMax-M2.5",
    "kimi-k2.5": "Kimi-K2.5",
    "qwen3.5-plus": "Qwen3.5-Plus",
    "doubao-seed-1.8": "Doubao-Seed-1.8",
}


class TabbitClient:
    def __init__(
        self,
        token_str: str,
        base_url: str | None = None,
        client_id: str | None = None,
        req_ctx: str | None = None,
    ):
        parts = token_str.split("|")
        self.jwt_token = parts[0]
        self.next_auth = parts[1] if len(parts) > 1 else None
        self.device_id = parts[2] if len(parts) > 2 else str(uuid.uuid4())
        self.user_id = self._extract_user_id(self.jwt_token)
        self.base_url = base_url or "https://web.tabbitbrowser.com"
        self.client_id = client_id or "e7fa44387b1238ef1f6f"
        # Observed from official client traffic: base64("0.29.49(1002949)")
        self.req_ctx = req_ctx or "MC4yOS40OSgxMDAyOTQ5KQ=="

        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=15, read=120, write=15, pool=15),
            follow_redirects=False,
            verify=False,
        )

    def _extract_user_id(self, token: str) -> str:
        try:
            seg = token.split(".")[1]
            seg += "=" * ((4 - len(seg) % 4) % 4)
            payload = json.loads(
                base64.urlsafe_b64decode(seg)
            )
            return payload.get("id", payload.get("sub", str(uuid.uuid4())))
        except Exception:
            return str(uuid.uuid4())

    def _get_headers(self, referer_path: str = "/newtab") -> dict:
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
            "sec-ch-ua": '"Not:A-Brand";v="99", "Tabbit";v="146", "Chromium";v="146"',
            "sec-ch-ua-platform": '"Windows"',
            "x-chrome-id-consistency-request": (
                f"version=1,client_id={self.client_id},"
                f"device_id={self.device_id},sync_account_id={self.user_id},"
                "signin_mode=all_accounts,signout_mode=show_confirmation"
            ),
            "referer": f"{self.base_url}{referer_path}",
        }

    def _get_cookies(self) -> dict:
        cookies = {
            "token": self.jwt_token,
            "user_id": self.user_id,
            "SAPISID": self.user_id,
            "managed": "tab_browser",
            "NEXT_LOCALE": "zh",
        }
        if self.next_auth:
            cookies["next-auth.session-token"] = self.next_auth
        return cookies

    def _build_chat_headers(self, referer_path: str) -> dict:
        now_ms = str(int(time.time() * 1000))
        nonce = hashlib.sha256(f"{now_ms}-{secrets.token_hex(16)}".encode()).hexdigest()
        return {
            **self._get_headers(referer_path),
            "Accept": "text/event-stream",
            "Content-Type": "application/json",
            "Origin": self.base_url,
            "Connection": "keep-alive",
            "Cache-Control": "no-cache",
            "x-nonce": nonce,
            "x-signature": str(uuid.uuid4()),
            "x-timestamp": now_ms,
            "x-req-ctx": self.req_ctx,
            "trace-id": str(uuid.uuid4()),
            "unique-uuid": str(uuid.uuid4()),
        }

    async def create_chat_session(self) -> str:
        router_state = [
            "",
            {
                "children": [
                    "chat",
                    {
                        "children": [
                            ["id", "new", "d"],
                            {"children": ["__PAGE__", {}, None, "refetch"]},
                            None,
                            None,
                        ]
                    },
                    None,
                    None,
                ]
            },
            None,
            None,
        ]
        headers = {
            **self._get_headers("/chat/new"),
            "rsc": "1",
            "next-router-state-tree": urllib.parse.quote(json.dumps(router_state)),
        }

        resp = await self.client.get(
            f"{self.base_url}/chat/new",
            params={"_rsc": "auto"},
            headers=headers,
            cookies=self._get_cookies(),
        )

        text = resp.text
        match = re.search(
            r"/chat/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
            text,
        )
        if match:
            return match.group(1)
        raise Exception("Failed to extract chat session_id from RSC response")

    async def send_message(
        self, session_id: str, content: str, model: str
    ) -> AsyncGenerator[dict, None]:
        payload = {
            "chat_session_id": session_id,
            "message_id": None,
            "content": content,
            "selected_model": model,
            "parallel_group_id": None,
            "task_name": "chat",
            "agent_mode": False,
            "metadatas": {
                "html_content": f"<p>{html.escape(content, quote=False)}</p>",
            },
            "references": [],
            "entity": {
                "key": hashlib.md5(b"").hexdigest(),
                "extras": {"type": "tab", "url": ""},
            },
        }
        headers = self._build_chat_headers(f"/chat/{session_id}")

        async with self.client.stream(
            "POST",
            f"{self.base_url}/api/v1/chat/completion",
            json=payload,
            headers=headers,
            cookies=self._get_cookies(),
        ) as resp:
            if resp.status_code != 200:
                body = await resp.aread()
                raise Exception(
                    f"Tabbit API error {resp.status_code}: {body.decode()}"
                )

            current_event = None
            async for line in resp.aiter_lines():
                if line.startswith("event:"):
                    current_event = line[len("event:") :].strip()
                elif line.startswith("data:") and current_event:
                    data_str = line[len("data:") :].strip()
                    try:
                        yield {"event": current_event, "data": json.loads(data_str)}
                    except Exception:
                        pass
                elif line.startswith("data:"):
                    # Some streams only emit data lines.
                    data_str = line[len("data:") :].strip()
                    if not data_str or data_str == "[DONE]":
                        continue
                    try:
                        data = json.loads(data_str)
                        # Normalize possible chunk/error shape.
                        if isinstance(data, dict) and data.get("error"):
                            yield {"event": "error", "data": data["error"]}
                        elif isinstance(data, dict) and "content" in data:
                            yield {"event": "message_chunk", "data": data}
                    except Exception:
                        pass

import time
import asyncio
from typing import Optional

from core.config import ConfigManager
from core.tabbit_client import TabbitClient

COOLDOWN_SECONDS = 300  # 5 分钟冷却
MAX_CONSECUTIVE_ERRORS = 3


class TokenManager:
    """
    Token 轮询与运行时统计。

    运行期计数（total_requests、连续失败、last_used、status）仅存内存，不写 config.json，
    避免每个请求刷盘。配置里的 tokens[] 仅保留用户显式保存的字段（名称、值、启用等）。
    """

    def __init__(self, config: ConfigManager):
        self.config = config
        self._clients: dict[str, TabbitClient] = {}
        self._index: int = 0
        self._cooldowns: dict[str, float] = {}  # token_id -> 冷却截止时间戳
        self._lock = asyncio.Lock()
        self._cached_available: list[dict] = []
        self._cache_ts = 0.0
        self._cache_ttl = 1.0
        # token_id -> 运行时统计（进程内；删除 token 时会 pop，避免泄漏）
        self._runtime: dict[str, dict] = {}

    @property
    def has_tokens(self) -> bool:
        return len(self.config.get("tokens", default=[])) > 0

    def _valid_token_ids(self) -> set[str]:
        return {t["id"] for t in self.config.get("tokens", default=[])}

    def _prune_runtime_locked(self):
        """删除已从配置中移除的 token 的运行时条目，防止字典无限增长。"""
        valid = self._valid_token_ids()
        for tid in list(self._runtime.keys()):
            if tid not in valid:
                self._runtime.pop(tid, None)
                self._cooldowns.pop(tid, None)

    def _get_available_tokens(self) -> list[dict]:
        tokens = self.config.get("tokens", default=[])
        now = time.time()
        available = []
        for t in tokens:
            if not t.get("enabled", True):
                continue
            cooldown_until = self._cooldowns.get(t["id"], 0)
            if now >= cooldown_until:
                if t["id"] in self._cooldowns:
                    del self._cooldowns[t["id"]]
                    rt = self._runtime.setdefault(
                        t["id"],
                        {
                            "total_requests": 0,
                            "error_streak": 0,
                            "last_used_at": None,
                            "status": "unknown",
                        },
                    )
                    rt["status"] = "unknown"
                    rt["error_streak"] = 0
                available.append(t)
        return available

    def _get_available_tokens_cached(self) -> list[dict]:
        now = time.time()
        if self._cached_available and (now - self._cache_ts) < self._cache_ttl:
            return self._cached_available
        self._cached_available = self._get_available_tokens()
        self._cache_ts = now
        return self._cached_available

    def _get_client(self, token_info: dict) -> TabbitClient:
        tid = token_info["id"]
        if tid not in self._clients:
            self._clients[tid] = TabbitClient(
                token_info["value"],
                self.config.get("tabbit", "base_url"),
                self.config.get("tabbit", "client_id"),
                self.config.get("tabbit", "req_ctx"),
            )
        return self._clients[tid]

    async def get_next(self) -> tuple[Optional[dict], Optional[TabbitClient]]:
        async with self._lock:
            self._prune_runtime_locked()
            available = self._get_available_tokens_cached()
            if not available:
                return None, None
            self._index = self._index % len(available)
            token_info = available[self._index]
            self._index = (self._index + 1) % len(available)
            client = self._get_client(token_info)
            return token_info, client

    async def report_success(self, token_id: str):
        async with self._lock:
            ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            r = self._runtime.setdefault(
                token_id,
                {
                    "total_requests": 0,
                    "error_streak": 0,
                    "last_used_at": None,
                    "status": "unknown",
                },
            )
            r["total_requests"] = r.get("total_requests", 0) + 1
            r["error_streak"] = 0
            r["last_used_at"] = ts
            r["status"] = "active"

    async def report_error(self, token_id: str):
        async with self._lock:
            r = self._runtime.setdefault(
                token_id,
                {
                    "total_requests": 0,
                    "error_streak": 0,
                    "last_used_at": None,
                    "status": "unknown",
                },
            )
            r["error_streak"] = r.get("error_streak", 0) + 1
            r["total_requests"] = r.get("total_requests", 0) + 1
            ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            r["last_used_at"] = ts
            if r["error_streak"] >= MAX_CONSECUTIVE_ERRORS:
                self._cooldowns[token_id] = time.time() + COOLDOWN_SECONDS
                r["status"] = "cooldown"
            else:
                r["status"] = "error"

    async def get_token_status(self, token_id: str) -> str:
        async with self._lock:
            now = time.time()
            cooldown_until = self._cooldowns.get(token_id, 0)
            if now < cooldown_until:
                return "cooldown"
            r = self._runtime.get(token_id)
            if r:
                return r.get("status", "unknown")
            return "unknown"

    async def runtime_overlay(self, token_id: str) -> dict:
        """供管理台合并展示：有运行数据则覆盖文件中的统计字段。"""
        async with self._lock:
            r = self._runtime.get(token_id)
            if not r:
                return {}
            return {
                "total_requests": r.get("total_requests", 0),
                "error_count": r.get("error_streak", 0),
                "last_used_at": r.get("last_used_at"),
            }

    async def record_test_outcome(self, token_id: str, ok: bool):
        """Token 测试按钮：只更新内存状态，不写盘。"""
        async with self._lock:
            r = self._runtime.setdefault(
                token_id,
                {
                    "total_requests": 0,
                    "error_streak": 0,
                    "last_used_at": None,
                    "status": "unknown",
                },
            )
            if ok:
                r["status"] = "active"
                r["error_streak"] = 0
            else:
                r["status"] = "error"

    async def remove_client(self, token_id: str):
        async with self._lock:
            client = self._clients.pop(token_id, None)
            self._cooldowns.pop(token_id, None)
            self._runtime.pop(token_id, None)
            self._cached_available = []
        if client:
            await client.client.aclose()

    async def close_all(self):
        async with self._lock:
            clients = list(self._clients.values())
            self._clients.clear()
            self._cooldowns.clear()
            self._cached_available = []
            self._runtime.clear()
        for client in clients:
            await client.client.aclose()

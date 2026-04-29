"""
对比 /chat/new 的 RSC 响应：旧版客户端指纹 vs 当前客户端指纹。

用途：判断「Failed to extract chat session_id」更像远端格式变化，还是本地请求特征变化导致。

用法（在项目根目录）:
  .venv\\Scripts\\python.exe scripts/compare_chat_new_rsc.py
  .venv\\Scripts\\python.exe scripts/compare_chat_new_rsc.py --token "jwt|next-auth|device"

不写 stdout 完整 token；仅打印 user_id 前后几位与响应摘要。
"""

from __future__ import annotations

import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import argparse
import base64
import json
import re
import sys
import urllib.parse
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SESSION_RE = re.compile(
    r"/chat/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"
)


def _mask(s: str, keep: int = 6) -> str:
    if not s or len(s) <= keep * 2:
        return s[:3] + "..." if len(s) > 3 else s
    return f"{s[:keep]}...{s[-keep:]}"


def extract_uid_new(jwt: str) -> str:
    try:
        seg = jwt.split(".")[1]
        seg += "=" * ((4 - len(seg) % 4) % 4)
        payload = json.loads(base64.urlsafe_b64decode(seg))
        return str(payload.get("id", payload.get("sub", "")))
    except Exception:
        return ""


def extract_uid_legacy(jwt: str) -> str:
    try:
        payload = json.loads(base64.urlsafe_b64decode(jwt.split(".")[1] + "=="))
        return str(payload.get("id", payload.get("sub", "")))
    except Exception:
        return ""


def load_token_from_config(path: Path) -> str:
    data = json.loads(path.read_text(encoding="utf-8"))
    for t in data.get("tokens") or []:
        if t.get("enabled", True) and t.get("value"):
            return t["value"]
    raise SystemExit("config.json 中没有可用的 enabled token")


def build_router_headers(
    base_url: str,
    referer_path: str,
    *,
    ua_146: bool,
    client_id: str,
    device_id: str,
    sync_account_id: str,
) -> dict:
    if ua_146:
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
        sec = '"Not:A-Brand";v="99", "Tabbit";v="146", "Chromium";v="146"'
    else:
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
        sec = '"Not:A-Brand";v="99", "Tabbit";v="145", "Chromium";v="145"'
    return {
        "User-Agent": ua,
        "sec-ch-ua": sec,
        "sec-ch-ua-platform": '"Windows"',
        "x-chrome-id-consistency-request": (
            f"version=1,client_id={client_id},"
            f"device_id={device_id},sync_account_id={sync_account_id},"
            "signin_mode=all_accounts,signout_mode=show_confirmation"
        ),
        "referer": f"{base_url}{referer_path}",
        "rsc": "1",
    }


def router_state_json():
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
    return urllib.parse.quote(json.dumps(router_state))


def fetch_chat_new(
    base_url: str,
    jwt: str,
    next_auth: str | None,
    *,
    ua_146: bool,
    use_sapisid: bool,
    user_id_for_cookie: str,
    client_id: str,
    device_id: str,
) -> tuple[int, str, str | None]:
    headers = build_router_headers(
        base_url,
        "/chat/new",
        ua_146=ua_146,
        client_id=client_id,
        device_id=device_id,
        sync_account_id=user_id_for_cookie,
    )
    headers["next-router-state-tree"] = router_state_json()
    cookies = {
        "token": jwt,
        "user_id": user_id_for_cookie,
        "managed": "tab_browser",
        "NEXT_LOCALE": "zh",
    }
    if use_sapisid:
        cookies["SAPISID"] = user_id_for_cookie
    if next_auth:
        cookies["next-auth.session-token"] = next_auth

    with httpx.Client(timeout=30, verify=False, follow_redirects=False) as client:
        r = client.get(
            f"{base_url}/chat/new",
            params={"_rsc": "auto"},
            headers=headers,
            cookies=cookies,
        )
    text = r.text
    m = SESSION_RE.search(text)
    sid = m.group(1) if m else None
    return r.status_code, text, sid


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--config",
        type=Path,
        default=ROOT / "config.json",
        help="读取第一个可用 token",
    )
    ap.add_argument("--token", type=str, default="", help="覆盖：jwt 或 jwt|next|device")
    ap.add_argument(
        "--base-url",
        default="https://web.tabbitbrowser.com",
        help="Tabbit Web 根地址",
    )
    args = ap.parse_args()

    raw = args.token.strip()
    if not raw:
        if not args.config.exists():
            raise SystemExit("请提供 --token 或有效的 --config")
        raw = load_token_from_config(args.config)

    parts = raw.split("|")
    jwt = parts[0]
    next_auth = parts[1] if len(parts) > 1 else None
    device_id = parts[2] if len(parts) > 2 else "00000000-0000-0000-0000-000000000001"
    client_id = "e7fa44387b1238ef1f6f"

    uid_legacy = extract_uid_legacy(jwt)
    uid_new = extract_uid_new(jwt)

    print("=== compare_chat_new_rsc ===")
    print(f"base_url: {args.base_url}")
    print(f"jwt sub/id legacy decode: {_mask(uid_legacy)}  (len={len(uid_legacy)})")
    print(f"jwt sub/id new decode:    {_mask(uid_new)}  (len={len(uid_new)})")
    if uid_legacy != uid_new:
        print("NOTE: legacy vs new JWT decode differ → cookies user_id / SAPISID may differ between profiles.")
    print()

    scenarios = [
        (
            "legacy_fingerprint",
            False,
            False,
            uid_legacy or uid_new,
            "UA145, no SAPISID, user_id=legacy_decode (fallback new)",
        ),
        (
            "current_fingerprint",
            True,
            True,
            uid_new or uid_legacy,
            "UA146, SAPISID, user_id=new_decode (fallback legacy)",
        ),
    ]

    rows = []
    for name, ua_146, sapisid, uid, note in scenarios:
        code, text, sid = fetch_chat_new(
            args.base_url,
            jwt,
            next_auth,
            ua_146=ua_146,
            use_sapisid=sapisid,
            user_id_for_cookie=uid,
            client_id=client_id,
            device_id=device_id,
        )
        has_path = "/chat/" in text
        preview = (text[:400].replace("\n", " ") + ("..." if len(text) > 400 else ""))
        rows.append((name, code, len(text), sid, has_path, note, preview))

    print(f"{'profile':<22} {'http':>4} {'bytes':>7} {'session_ok':>10} {'has_/chat/':>11}  note")
    for name, code, ln, sid, has_path, note, preview in rows:
        ok = "yes" if sid else "no"
        hp = "yes" if has_path else "no"
        print(f"{name:<22} {code:>4} {ln:>7} {ok:>10} {hp:>11}  {note}")
        if code != 200 or not sid:
            print(f"  response_preview: {preview!r}")
    print()

    a_ok = rows[0][3] is not None
    b_ok = rows[1][3] is not None
    a_code = rows[0][1]
    b_code = rows[1][1]

    # Conclusion (zh-CN; avoid relying on console codepage for logic)
    if a_code != 200 and b_code != 200 and a_code == b_code:
        print(
            f"[结论] 两种指纹 HTTP 均为 {a_code}，响应长度一致 → "
            "优先怀疑鉴权/封禁/ Cookie 失效或远端统一拦请求，不是「旧 UA 能过、新 UA 不过」这种分叉。"
        )
    elif a_ok and not b_ok:
        print(
            "[结论] 旧指纹能解析 session、当前指纹不能 → 更像本地请求特征变化影响了返回体。"
        )
    elif not a_ok and b_ok:
        print("[结论] 旧指纹失败、当前成功 → 请复查 token 或多跑几次排除抖动。")
    elif a_ok and b_ok:
        print(
            "[结论] 两种指纹都能解析 session → 端到端问题更可能在后续步骤（如 completion），而非 create_chat_session。"
        )
    else:
        print(
            "[结论] 两种指纹都未解析到 session，但 HTTP 状态不一致或需看 preview → "
            "结合上方 preview 判断是 HTML 登录页、错误页还是 RSC 格式变化。"
        )


if __name__ == "__main__":
    main()

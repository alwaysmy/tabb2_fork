import asyncio
import base64
import ctypes
import json
import sqlite3
import tempfile
import shutil
import time
from pathlib import Path
from urllib.parse import quote

import httpx
from Crypto.Cipher import AES


LOCAL_APPDATA = Path.home() / "AppData" / "Local" / "Tabbit" / "User Data"
LOCAL_STATE = LOCAL_APPDATA / "Local State"
COOKIES_DB = LOCAL_APPDATA / "Default" / "Network" / "Cookies"
BASE_URL = "https://web.tabbitbrowser.com"
CLIENT_ID = "e7fa44387b1238ef1f6f"


class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_uint), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _crypt_unprotect(data: bytes) -> bytes:
    in_blob = DATA_BLOB(len(data), ctypes.cast(ctypes.create_string_buffer(data), ctypes.POINTER(ctypes.c_char)))
    out_blob = DATA_BLOB()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    if not crypt32.CryptUnprotectData(ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)):
        raise ctypes.WinError()
    try:
        ptr = ctypes.cast(out_blob.pbData, ctypes.POINTER(ctypes.c_char * out_blob.cbData))
        return bytes(ptr.contents)
    finally:
        kernel32.LocalFree(out_blob.pbData)


def _get_master_key() -> bytes:
    state = json.loads(LOCAL_STATE.read_text(encoding="utf-8"))
    enc_key = base64.b64decode(state["os_crypt"]["encrypted_key"])
    if enc_key.startswith(b"DPAPI"):
        enc_key = enc_key[5:]
    return _crypt_unprotect(enc_key)


def _decrypt_cookie(enc: bytes, master_key: bytes) -> str:
    if enc.startswith(b"v10") or enc.startswith(b"v11"):
        nonce = enc[3:15]
        ciphertext = enc[15:-16]
        tag = enc[-16:]
        cipher = AES.new(master_key, AES.MODE_GCM, nonce=nonce)
        return cipher.decrypt_and_verify(ciphertext, tag).decode("utf-8", errors="ignore")
    return _crypt_unprotect(enc).decode("utf-8", errors="ignore")


def load_domain_cookies() -> dict:
    master_key = _get_master_key()
    db_path = COOKIES_DB
    # If locked, copy to temp and read from copy.
    if not db_path.exists():
        raise FileNotFoundError(str(db_path))
    temp_copy = None
    for _ in range(5):
        try:
            temp_copy = Path(tempfile.gettempdir()) / f"tabbit_cookies_{int(time.time()*1000)}.db"
            shutil.copy2(db_path, temp_copy)
            db_path = temp_copy
            break
        except Exception:
            time.sleep(0.3)
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute(
        """
        SELECT host_key, name, encrypted_value
        FROM cookies
        WHERE host_key LIKE '%tabbitbrowser.com'
           OR host_key LIKE '%tab-browser.com'
        """
    )
    rows = cur.fetchall()
    conn.close()
    if temp_copy and temp_copy.exists():
        try:
            temp_copy.unlink()
        except Exception:
            pass
    cookies = {}
    for host_key, name, enc in rows:
        try:
            cookies[name] = _decrypt_cookie(enc, master_key)
        except Exception:
            pass
    # Keep only cookies relevant to Tabbit auth/session and safe ASCII values.
    keep = {"token", "next-auth.session-token", "user_id", "managed", "NEXT_LOCALE"}
    out = {}
    for k, v in cookies.items():
        if k not in keep:
            continue
        try:
            v.encode("ascii")
        except Exception:
            continue
        out[k] = v
    return out


async def main():
    cookies = load_domain_cookies()
    print("COOKIE_NAMES", sorted(cookies.keys())[:20], "...")
    print("HAS_token", "token" in cookies, "HAS_next_auth", "next-auth.session-token" in cookies)

    if "token" not in cookies:
        print("NO_TOKEN_COOKIE")
        return

    jwt = cookies["token"]
    user_id = None
    try:
        payload = json.loads(base64.urlsafe_b64decode(jwt.split(".")[1] + "=="))
        user_id = payload.get("id") or payload.get("sub")
    except Exception:
        user_id = "unknown"

    headers_common = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
        "sec-ch-ua": '"Not:A-Brand";v="99", "Tabbit";v="145", "Chromium";v="145"',
        "sec-ch-ua-platform": '"Windows"',
        "x-chrome-id-consistency-request": (
            f"version=1,client_id={CLIENT_ID},"
            f"device_id=probe-{user_id},sync_account_id={user_id},"
            "signin_mode=all_accounts,signout_mode=show_confirmation"
        ),
    }

    async with httpx.AsyncClient(timeout=30, verify=False, follow_redirects=False) as client:
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
        h1 = {
            **headers_common,
            "referer": f"{BASE_URL}/chat/new",
            "rsc": "1",
            "next-router-state-tree": quote(json.dumps(router_state)),
        }
        r1 = await client.get(f"{BASE_URL}/chat/new", params={"_rsc": "auto"}, headers=h1, cookies=cookies)
        print("CHAT_NEW_STATUS", r1.status_code, "LEN", len(r1.text))
        if "/chat/" not in r1.text:
            print("CHAT_NEW_NO_SESSION_MARKER")
            print(r1.text[:300])
            return
        import re
        m = re.search(r"/chat/([0-9a-f-]{36})", r1.text)
        if not m:
            print("NO_SESSION_ID")
            return
        sid = m.group(1)
        print("SESSION_ID", sid)

        payload = {
            "chat_session_id": sid,
            "content": "reply OK only",
            "selected_model": "最佳",
            "agent_mode": False,
            "metadatas": {"html_content": "<p>reply OK only</p>"},
            "entity": {"key": "d41d8cd98f00b204e9800998ecf8427e", "extras": {"type": "tab", "url": ""}},
        }
        h2 = {
            **headers_common,
            "referer": f"{BASE_URL}/chat/{sid}",
            "Accept": "text/event-stream",
            "Content-Type": "application/json",
        }
        async with client.stream("POST", f"{BASE_URL}/chat/send", headers=h2, cookies=cookies, json=payload) as r2:
            print("CHAT_SEND_STATUS", r2.status_code)
            n = 0
            async for line in r2.aiter_lines():
                if line.strip():
                    print("SSE", line[:240])
                    n += 1
                if n >= 20:
                    break


if __name__ == "__main__":
    asyncio.run(main())

"""Dcard（實驗性）：Dcard 常用 Cloudflare 擋掉程式存取，失敗時只會跳過。"""
import time
from datetime import datetime, timedelta

import requests

from . import TZ, UA, Item

API = "https://www.dcard.tw/service/api/v2"


def fetch(forums, lookback_hours=30, limit=60):
    cutoff = datetime.now(TZ) - timedelta(hours=lookback_hours)
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept": "application/json"})
    items = []
    for forum in forums:
        try:
            r = s.get(f"{API}/forums/{forum}/posts", params={"limit": min(limit, 100)}, timeout=20)
            r.raise_for_status()
            posts = r.json()
        except Exception as e:  # noqa: BLE001
            print(f"[Dcard] {forum} 版無法讀取（可能被阻擋），略過：{e}")
            continue
        n = 0
        for p in posts:
            published = datetime.fromisoformat(p["createdAt"].replace("Z", "+00:00"))
            if published < cutoff:
                continue
            text = p.get("excerpt", "")
            try:
                time.sleep(0.5)
                d = s.get(f"{API}/posts/{p['id']}", timeout=20)
                if d.ok:
                    text = d.json().get("content", text)
            except Exception:  # noqa: BLE001
                pass
            items.append(Item(id=f"dcard:{p['id']}", source="dcard", kind="post",
                              url=f"https://www.dcard.tw/f/{forum}/p/{p['id']}",
                              title=p.get("title", ""), author=p.get("school") or "匿名",
                              published=published, text=text))
            n += 1
        print(f"[Dcard] {forum} 版：取得 {n} 篇")
    return items

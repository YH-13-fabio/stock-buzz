"""PTT 爬蟲：讀 ptt.cc 網頁版的看板列表與文章內容（含推文）。"""
import re
import time
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup

from . import TZ, UA, Comment, Item

BASE = "https://www.ptt.cc"


def _session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
        "Referer": "https://www.ptt.cc/bbs/index.html",
    })
    s.cookies.set("over18", "1", domain=".ptt.cc")
    return s


def _describe_error(e):
    """出錯時多印一點伺服器資訊，方便判斷是被擋 IP 還是其他問題。"""
    resp = getattr(e, "response", None)
    if resp is None:
        return str(e)
    return (f"HTTP {resp.status_code}（server={resp.headers.get('server', '?')}，"
            f"內容開頭：{resp.text[:120].strip()!r}）")


def parse_index(html):
    """解析看板列表頁，回傳 (文章清單, 上一頁網址)。置底文會被排除。"""
    soup = BeautifulSoup(html, "html.parser")
    posts = []
    container = soup.select_one("div.r-list-container")
    elements = container.find_all("div", recursive=False) if container else soup.select("div.r-ent")
    for el in elements:
        if "r-list-sep" in (el.get("class") or []):
            break  # 分隔線以下是置底文
        if "r-ent" not in (el.get("class") or []):
            continue
        a = el.select_one("div.title a")
        if not a:
            continue  # 已刪除的文章
        date = el.select_one("div.date").get_text(strip=True)
        posts.append({"url": BASE + a["href"], "title": a.get_text(strip=True), "date": date})
    prev = None
    for a in soup.select("div.btn-group-paging a"):
        if "上頁" in a.get_text() and a.get("href"):
            prev = BASE + a["href"]
    return posts, prev


def parse_article(html, url):
    """解析單篇文章。回傳 Item，或 None（格式異常）。"""
    soup = BeautifulSoup(html, "html.parser")
    main = soup.select_one("#main-content")
    if main is None:
        return None
    meta = {}
    for line in main.select("div.article-metaline"):
        tag = line.select_one(".article-meta-tag")
        val = line.select_one(".article-meta-value")
        if tag and val:
            meta[tag.get_text(strip=True)] = val.get_text(strip=True)
    try:
        published = datetime.strptime(meta.get("時間", ""), "%a %b %d %H:%M:%S %Y").replace(tzinfo=TZ)
    except ValueError:
        return None

    comments = []
    for p in main.select("div.push"):
        tag = p.select_one(".push-tag")
        user = p.select_one(".push-userid")
        content = p.select_one(".push-content")
        if tag and content:
            comments.append(Comment(tag.get_text(strip=True), user.get_text(strip=True) if user else "",
                                    content.get_text(strip=True).lstrip(":").strip()))

    for sel in ("div.article-metaline", "div.article-metaline-right", "div.push"):
        for el in main.select(sel):
            el.decompose()
    body = main.get_text("\n")
    body = body.split("※ 發信站")[0].split("\n--\n")[0].strip()

    m = re.search(r"/bbs/[^/]+/(M\.\d+\.A\.[0-9A-Z]+)\.html", url)
    pid = m.group(1) if m else url
    return Item(id=f"ptt:{pid}", source="ptt", kind="post", url=url,
                title=meta.get("標題", ""), author=meta.get("作者", "").split(" ")[0],
                published=published, text=body, comments=comments)


def _index_date_older_than(mmdd, cutoff):
    """列表頁只有「月/日」，用今年（跨年時用去年）判斷是否早於截止日。"""
    try:
        mo, d = (int(x) for x in mmdd.strip().split("/"))
    except ValueError:
        return False
    now = datetime.now(TZ)
    year = now.year if (mo, d) <= (now.month, now.day) else now.year - 1
    return datetime(year, mo, d, 23, 59, 59, tzinfo=TZ) < cutoff


def fetch(boards, lookback_hours=30, max_pages=20, delay=0.4):
    s = _session()
    cutoff = datetime.now(TZ) - timedelta(hours=lookback_hours)
    items = []
    for board in boards:
        url = f"{BASE}/bbs/{board}/index.html"
        seen = 0
        for _ in range(max_pages):
            try:
                r = s.get(url, timeout=20)
                r.raise_for_status()
            except Exception as e:  # noqa: BLE001
                print(f"[PTT] 讀取列表失敗 {url}：{_describe_error(e)}")
                break
            posts, prev = parse_index(r.text)
            if posts and all(_index_date_older_than(p["date"], cutoff) for p in posts):
                break
            for p in reversed(posts):
                if p["title"].startswith("[公告]") or _index_date_older_than(p["date"], cutoff):
                    continue
                time.sleep(delay)
                try:
                    ar = s.get(p["url"], timeout=20)
                    ar.raise_for_status()
                except Exception as e:  # noqa: BLE001
                    print(f"[PTT] 讀取文章失敗 {p['url']}：{e}")
                    continue
                item = parse_article(ar.text, p["url"])
                if item and item.published >= cutoff:
                    items.append(item)
                    seen += 1
            if not prev:
                break
            url = prev
            time.sleep(delay)
        print(f"[PTT] {board} 板：取得 {seen} 篇")
    return items

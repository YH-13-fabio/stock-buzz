"""把資料庫整理成 docs/data.json，給 Dashboard 網頁讀取。"""
import json
from pathlib import Path
from datetime import date, datetime, timedelta

from . import TZ
from .finmind import estimate_maintenance
from .indicators import summarize

DAYS = 35  # Dashboard 保留最近幾天的每日資料


def build(db, stocks, out_path):
    today = datetime.now(TZ).date()
    row = db.conn.execute("SELECT MAX(date) FROM mentions").fetchone()
    latest = date.fromisoformat(row[0]) if row and row[0] else today
    latest = min(latest, today)
    days = [(latest - timedelta(days=i)).isoformat() for i in range(DAYS - 1, -1, -1)]

    daily = {d: {} for d in days}
    for d, code, src, n, bull, bear in db.conn.execute(
        """SELECT date, code, source, COUNT(*),
                  SUM(sentiment = 1), SUM(sentiment = -1)
           FROM mentions WHERE date >= ? AND date <= ?
           GROUP BY date, code, source""", (days[0], days[-1])):
        daily[d].setdefault(code, {})[src] = [n, bull, bear]

    week_start = (latest - timedelta(days=6)).isoformat()
    items = {}
    for code, sent, src, title, url, d in db.conn.execute(
        """SELECT m.code, m.sentiment, i.source, i.title, i.url, i.date
           FROM mentions m JOIN items i ON i.id = m.item_id
           WHERE m.date >= ? ORDER BY i.published DESC""", (week_start,)):
        lst = items.setdefault(code, [])
        if len(lst) < 10:
            lst.append({"t": title, "u": url, "s": sent, "src": src, "d": d})

    counts = {}
    for d, src, n in db.conn.execute(
        "SELECT date, source, COUNT(*) FROM items WHERE date >= ? GROUP BY date, source", (days[0],)):
        counts.setdefault(d, {})[src] = n

    codes = {c for d in daily.values() for c in d}

    prices = {}
    tables = {r[0] for r in db.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    kdir = Path(out_path).parent / "k"
    kdir.mkdir(exist_ok=True)
    if "prices" in tables:
        for code in codes:
            bars = db.conn.execute(
                "SELECT date, open, high, low, close, volume FROM prices WHERE code=? ORDER BY date",
                (code,)).fetchall()
            summary = summarize(bars[-200:])
            if not summary:
                continue
            summary.pop("series", None)
            prices[code] = summary
            write_kline(db, code, bars, kdir, "margin" in tables)
    data = {
        "generated_at": datetime.now(TZ).isoformat(timespec="minutes"),
        "latest_date": latest.isoformat(),
        "days": days,
        "names": {c: stocks.get(c, {}).get("name", c) for c in sorted(codes)},
        "daily": daily,
        "items": items,
        "item_counts": counts,
        "prices": prices,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"[網頁資料] 已輸出 {out_path}（{len(codes)} 檔股票、{len(prices)} 檔有股價、最新日期 {latest}）")


def write_kline(db, code, bars, kdir, has_margin):
    """每檔股票一個 K 線檔（docs/k/代號.json），網頁點選時才載入。"""
    mm, src = {}, "none"
    if has_margin:
        rows = db.conn.execute(
            "SELECT date, balance, maintenance, source FROM margin WHERE code=? ORDER BY date",
            (code,)).fetchall()
        official = {d: m for d, _, m, s in rows if s == "official" and m is not None}
        if official:
            mm, src = official, "official"
        elif rows:
            by_date = {b[0]: b[1:] for b in bars}
            mm = estimate_maintenance(by_date, [(d, b) for d, b, _, _ in rows if b is not None])
            src = "estimate" if mm else "none"
    data = {
        "code": code,
        "d": [b[0] for b in bars],
        "o": [round(b[1], 2) for b in bars],
        "h": [round(b[2], 2) for b in bars],
        "l": [round(b[3], 2) for b in bars],
        "c": [round(b[4], 2) for b in bars],
        "v": [int(b[5]) for b in bars],
        "mm": [mm.get(b[0]) for b in bars],
        "mm_src": src,
    }
    with open(kdir / f"{code}.json", "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))
"""把資料庫整理成 docs/data.json，給 Dashboard 網頁讀取。"""
import json
from datetime import date, datetime, timedelta

from . import TZ
from .indicators import summarize

DAYS = 35  # Dashboard 保留最近幾天的每日資料


def build(db, stocks, out_path):
    today = datetime.now(TZ).date()
    row = db.conn.execute("SELECT MAX(date) FROM mentions").fetchone()
    latest = date.fromisoformat(row[0]) if row and row[0] else today
    latest = min(latest, today)
    days = [(latest - timedelta(days=i)).isoformat() for i in range(DAYS - 1, -1, -1)]

    daily = {d: {} for d in days}
    for d, code, src, n, bull, bear in db.conn.execute(
        """SELECT date, code, source, COUNT(*),
                  SUM(sentiment = 1), SUM(sentiment = -1)
           FROM mentions WHERE date >= ? AND date <= ?
           GROUP BY date, code, source""", (days[0], days[-1])):
        daily[d].setdefault(code, {})[src] = [n, bull, bear]

    week_start = (latest - timedelta(days=6)).isoformat()
    items = {}
    for code, sent, src, title, url, d in db.conn.execute(
        """SELECT m.code, m.sentiment, i.source, i.title, i.url, i.date
           FROM mentions m JOIN items i ON i.id = m.item_id
           WHERE m.date >= ? ORDER BY i.published DESC""", (week_start,)):
        lst = items.setdefault(code, [])
        if len(lst) < 10:
            lst.append({"t": title, "u": url, "s": sent, "src": src, "d": d})

    counts = {}
    for d, src, n in db.conn.execute(
        "SELECT date, source, COUNT(*) FROM items WHERE date >= ? GROUP BY date, source", (days[0],)):
        counts.setdefault(d, {})[src] = n

    codes = {c for d in daily.values() for c in d}

    prices = {}
    has_prices = db.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='prices'").fetchone()
    if has_prices:
        for code in codes:
            bars = db.conn.execute(
                "SELECT date, open, high, low, close, volume FROM prices WHERE code=? ORDER BY date DESC LIMIT 200",
                (code,)).fetchall()[::-1]
            summary = summarize(bars)
            if summary:
                prices[code] = summary
    data = {
        "generated_at": datetime.now(TZ).isoformat(timespec="minutes"),
        "latest_date": latest.isoformat(),
        "days": days,
        "names": {c: stocks.get(c, {}).get("name", c) for c in sorted(codes)},
        "daily": daily,
        "items": items,
        "item_counts": counts,
        "prices": prices,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"[網頁資料] 已輸出 {out_path}（{len(codes)} 檔股票、{len(prices)} 檔有股價、最新日期 {latest}）")

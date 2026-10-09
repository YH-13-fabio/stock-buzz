"""永豐金 Shioaji：抓被討論股票的日線股價（由 1 分 K 合成）。

需要在 GitHub Secrets 設定：
    SHIOAJI_API_KEY、SHIOAJI_SECRET_KEY
沒設定或登入失敗時會自動跳過，不影響爬文。

Shioaji 限制（官方文件）：
- K 線是 1 分鐘線，單次查詢區間最多 30 天
- 沒有透過 API 下單的帳號，每日行情流量上限 500MB（每個交易日早上 8 點重置）
- 行情查詢每 10 秒最多 50 次；請在收盤後查歷史資料
"""
import os
import time
from collections import OrderedDict
from datetime import date, datetime, timedelta, timezone

from . import TZ

SCHEMA = """
CREATE TABLE IF NOT EXISTS prices (
    code TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, volume INTEGER,
    PRIMARY KEY (code, date)
);
"""
MIN_REMAINING_MB = 60     # 剩餘流量低於這個值就停止補歷史資料


def _kbars_rows(kbars):
    """把 Shioaji 回傳的 Kbars 轉成 [(datetime, o, h, l, c, v), ...]，相容新舊版本。"""
    if hasattr(kbars, "dict"):
        d = kbars.dict()
    else:
        try:
            d = dict(kbars)
        except Exception:  # noqa: BLE001
            d = {k: getattr(kbars, k) for k in ("ts", "Open", "High", "Low", "Close", "Volume")}
    ts = d.get("ts") or d.get("datetime") or []
    rows = []
    for i, t in enumerate(ts):
        if isinstance(t, (int, float)):
            # Shioaji 的 ts 是奈秒，且已是台灣當地時間
            sec = t / 1e9 if t > 1e12 else t
            dt = datetime.fromtimestamp(sec, timezone.utc).replace(tzinfo=None)
        else:
            dt = datetime.fromisoformat(str(t).replace("Z", ""))
        rows.append((dt, d["Open"][i], d["High"][i], d["Low"][i], d["Close"][i], d["Volume"][i]))
    return rows


def to_daily(rows):
    """1 分 K → 日 K：開＝第一根開、高＝最高、低＝最低、收＝最後一根收、量＝加總。"""
    days = OrderedDict()
    for dt, o, h, l, c, v in sorted(rows):
        k = dt.strftime("%Y-%m-%d")
        if k not in days:
            days[k] = [o, h, l, c, v]
        else:
            x = days[k]
            x[1] = max(x[1], h)
            x[2] = min(x[2], l)
            x[3] = c
            x[4] += v
    return days


class PriceFetcher:
    def __init__(self, db, cfg):
        self.db = db
        self.cfg = cfg
        self.api = None
        db.conn.executescript(SCHEMA)

    def login(self):
        # 去掉貼上時不小心多帶的空白或換行
        key = (os.environ.get("SHIOAJI_API_KEY") or "").strip()
        secret = (os.environ.get("SHIOAJI_SECRET_KEY") or "").strip()
        if not key or not secret:
            print("[股價] 沒有設定 SHIOAJI_API_KEY / SHIOAJI_SECRET_KEY，略過股價")
            return False
        try:
            import shioaji as sj
            self.api = sj.Shioaji(simulation=False)
            try:
                self.api.login(api_key=key, secret_key=secret, subscribe_trade=False)
            except TypeError:  # 舊版沒有 subscribe_trade 參數
                self.api.login(api_key=key, secret_key=secret)
            print(f"[股價] 永豐 Shioaji 登入成功（版本 {getattr(sj, '__version__', '?')}）")
            return True
        except Exception as e:  # noqa: BLE001
            print(f"[股價] Shioaji 登入失敗，略過股價：{e}")
            self.api = None
            return False

    def logout(self):
        if self.api:
            try:
                self.api.logout()
            except Exception:  # noqa: BLE001
                pass

    def _contract(self, code):
        api = self.api
        try:
            if hasattr(api, "contracts") and hasattr(api.contracts, "get"):
                c = api.contracts.get(code)
                if c is not None:
                    return c
        except Exception:  # noqa: BLE001
            pass
        try:
            return api.Contracts.Stocks[code]
        except Exception:  # noqa: BLE001
            return None

    def _remaining_mb(self):
        try:
            u = self.api.usage()
            rem = getattr(u, "remaining_bytes", None)
            if rem is None and isinstance(u, dict):
                rem = u.get("remaining_bytes")
            return rem / 1024 / 1024 if rem is not None else None
        except Exception:  # noqa: BLE001
            return None

    def _fetch_range(self, contract, start, end):
        rows = []
        cur = start
        while cur <= end:
            stop = min(cur + timedelta(days=29), end)
            try:
                k = self.api.kbars(contract=contract, start=cur.isoformat(), end=stop.isoformat())
                rows += _kbars_rows(k)
            except Exception as e:  # noqa: BLE001
                print(f"[股價] {contract.code} {cur}~{stop} 查詢失敗：{e}")
            time.sleep(0.3)  # 每 10 秒 50 次的限制內
            cur = stop + timedelta(days=1)
        return rows

    def update(self, codes):
        """更新這些股票的日線。已有歷史的只補最近幾天；新股票補 history_days 天。"""
        if not codes or not self.login():
            return 0
        history_days = int(self.cfg.get("history_days", 150))
        backfill_limit = int(self.cfg.get("max_backfill_per_run", 25))
        today = datetime.now(TZ).date()
        updated = backfilled = 0
        try:
            for code in codes:
                contract = self._contract(code)
                if contract is None:
                    continue
                last = self.db.conn.execute(
                    "SELECT MAX(date), COUNT(*) FROM prices WHERE code=?", (code,)).fetchone()
                has_history = last[0] and last[1] >= 30
                if has_history:
                    start = date.fromisoformat(last[0]) - timedelta(days=1)
                else:
                    if backfilled >= backfill_limit:
                        continue
                    rem = self._remaining_mb()
                    if rem is not None and rem < MIN_REMAINING_MB:
                        print(f"[股價] 今日流量剩 {rem:.0f}MB，暫停補歷史資料，明天會繼續")
                        backfill_limit = 0
                        continue
                    start = today - timedelta(days=history_days)
                    backfilled += 1
                daily = to_daily(self._fetch_range(contract, start, today))
                self.db.conn.executemany(
                    "INSERT OR REPLACE INTO prices VALUES (?,?,?,?,?,?,?)",
                    [(code, d, o, h, l, c, int(v)) for d, (o, h, l, c, v) in daily.items()])
                updated += 1 if daily else 0
            self.db.commit()
        finally:
            rem = self._remaining_mb()
            if rem is not None:
                print(f"[股價] 今日行情流量剩餘約 {rem:.0f}MB")
            self.logout()
        print(f"[股價] 更新 {updated} 檔（其中新補歷史 {backfilled} 檔）")
        return updated


def target_codes(db, days=7, limit=80):
    """要抓股價的股票：最近 N 天提及次數最多的前 limit 檔（ETF 也包含）。"""
    since = (datetime.now(TZ).date() - timedelta(days=days)).isoformat()
    return [r[0] for r in db.conn.execute(
        "SELECT code, COUNT(*) n FROM mentions WHERE date >= ? GROUP BY code ORDER BY n DESC LIMIT ?",
        (since, limit))]

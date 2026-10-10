"""FinMind：日 K（TaiwanStockPrice）、融資餘額、融資維持率。

需要在 GitHub Secrets 設定 FINMIND_TOKEN。
- TaiwanStockPrice、TaiwanStockMarginPurchaseShortSale：免費會員可用
- TaiwanStockMarginMaintenance（個股融資維持率）：需要 sponsor 等級；
  沒有權限時，改用融資餘額變化「估算」（見 estimate_maintenance）
"""
import os
import time
from datetime import date, datetime, timedelta

import requests

from . import TZ

API = "https://api.finmindtrade.com/api/v4/data"
SCHEMA = """
CREATE TABLE IF NOT EXISTS prices (
    code TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, volume INTEGER,
    PRIMARY KEY (code, date)
);
CREATE TABLE IF NOT EXISTS margin (
    code TEXT, date TEXT, balance INTEGER, maintenance REAL, source TEXT,
    PRIMARY KEY (code, date)
);
"""


class FinMind:
    def __init__(self, db, cfg):
        self.db = db
        self.cfg = cfg
        self.token = (os.environ.get("FINMIND_TOKEN") or "").strip()
        self.session = requests.Session()
        if self.token:
            self.session.headers["Authorization"] = f"Bearer {self.token}"
        self.calls = 0
        self.official_mm = True   # 第一次被拒絕後就不再嘗試官方維持率
        db.conn.executescript(SCHEMA)

    @property
    def enabled(self):
        return bool(self.token)

    def _get(self, dataset, code, start, end):
        """回傳 (資料列 list, 錯誤訊息或 None)。"""
        self.calls += 1
        try:
            r = self.session.get(API, params={"dataset": dataset, "data_id": code,
                                              "start_date": start, "end_date": end}, timeout=60)
            j = r.json()
        except Exception as e:  # noqa: BLE001
            return [], str(e)
        finally:
            time.sleep(0.4)
        if r.status_code != 200 or j.get("status") not in (200, None):
            return [], f"HTTP {r.status_code} {str(j.get('msg', ''))[:120]}"
        return j.get("data") or [], None

    # ---------------- 日 K ----------------
    def update_prices(self, code, years):
        today = datetime.now(TZ).date()
        last = self.db.conn.execute(
            "SELECT MAX(date), COUNT(*) FROM prices WHERE code=? AND date < ?",
            (code, (today - timedelta(days=200)).isoformat())).fetchone()
        # 已經有超過半年前的資料 → 只補最近 10 天；否則一次補 years 年
        if last[1]:
            start = today - timedelta(days=10)
        else:
            start = today - timedelta(days=int(365 * years))
        rows, err = self._get("TaiwanStockPrice", code, start.isoformat(), today.isoformat())
        if err:
            return f"{code} 日K失敗：{err}"
        data = []
        for r in rows:
            try:
                if float(r.get("close") or 0) > 0:
                    data.append((code, r["date"], float(r["open"]), float(r["max"]), float(r["min"]),
                                 float(r["close"]), int(float(r.get("Trading_Volume") or 0) / 1000)))  # 股→張
            except (KeyError, TypeError, ValueError):
                continue
        self.db.conn.executemany("INSERT OR REPLACE INTO prices VALUES (?,?,?,?,?,?,?)", data)
        return None

    # ---------------- 融資 ----------------
    def update_margin(self, code, years):
        today = datetime.now(TZ).date()
        have = self.db.conn.execute("SELECT COUNT(*) FROM margin WHERE code=?", (code,)).fetchone()[0]
        start = today - timedelta(days=15 if have > 100 else int(365 * years))
        rows, err = self._get("TaiwanStockMarginPurchaseShortSale", code,
                              start.isoformat(), today.isoformat())
        if err:
            return f"{code} 融資餘額失敗：{err}"
        self.db.conn.executemany(
            "INSERT INTO margin (code, date, balance, maintenance, source) VALUES (?,?,?,NULL,NULL) "
            "ON CONFLICT(code, date) DO UPDATE SET balance=excluded.balance",
            [(code, r["date"], int(float(r.get("MarginPurchaseTodayBalance") or 0))) for r in rows
             if r.get("date")])

        if self.official_mm:
            mm, err = self._get("TaiwanStockMarginMaintenance", code,
                                start.isoformat(), today.isoformat())
            if err or not mm:
                self.official_mm = False
                return f"個股融資維持率官方資料無法取得（{err or '無資料'}），改用估算"
            key = next((k for k in mm[0] if "aintenance" in k or "ratio" in k.lower()), None)
            if key:
                self.db.conn.executemany(
                    "UPDATE margin SET maintenance=?, source='official' WHERE code=? AND date=?",
                    [(float(r[key]), code, r["date"]) for r in mm if r.get(key) not in (None, "")])
        return None

    def update(self, codes):
        if not self.enabled:
            print("[FinMind] 沒有設定 FINMIND_TOKEN，略過（K 線改用永豐資料）")
            return False
        years = float(self.cfg.get("history_years", 5))
        errors = []
        for code in codes:
            for fn in (self.update_prices, self.update_margin):
                msg = fn(code, years)
                if msg:
                    errors.append(msg)
            self.db.commit()
        for m in dict.fromkeys(errors).keys():
            print(f"[FinMind] {m}")
        mm_src = "官方" if self.official_mm else "估算"
        print(f"[FinMind] 更新 {len(codes)} 檔日K與融資資料（呼叫 {self.calls} 次，融資維持率：{mm_src}）")
        return True


def estimate_maintenance(bars, balances, financing_ratio=0.6):
    """用融資餘額變化估算個股融資維持率（%）。

    做法：追蹤「融資平均成本」——餘額增加時，用當天均價 (高+低+收)/3 加權進成本；
    餘額減少時成本不變。維持率 ≈ 收盤價 ÷ (平均成本 × 融資成數) × 100。
    這是常見的近似算法，跟券商實際數字會有落差，只適合看趨勢。
    bars: {date: (o,h,l,c,v)}；balances: [(date, balance)] 依日期排序（單位：張）。
    """
    out = {}
    cost, prev = None, 0
    for d, bal in balances:
        bar = bars.get(d)
        if not bar:
            continue
        _, h, l, c, _ = bar
        typical = (h + l + c) / 3
        if cost is None or prev <= 0:
            cost = typical
        elif bal > prev:
            cost = (cost * prev + typical * (bal - prev)) / bal
        prev = bal
        if bal > 0 and cost:
            out[d] = round(c / (cost * financing_ratio) * 100, 1)
    return out

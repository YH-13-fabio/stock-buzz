"""上市櫃股票清單與「文章裡提到哪些股票」的辨識。"""
import csv
import re
from pathlib import Path

import requests

from . import UA

TWSE_URL = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
TPEX_URL = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes"
CODE_OK = re.compile(r"^(?:\d{4}|00\d{3}[A-Z]?)$")

DATA = Path(__file__).resolve().parent.parent / "data"
CACHE = DATA / "stocks.csv"
FALLBACK = DATA / "stocks_fallback.csv"


def _read_csv(path):
    with open(path, encoding="utf-8") as f:
        return {r["code"]: {"name": r["name"], "market": r.get("market", "")}
                for r in csv.DictReader(f)}


def load_stocks():
    """從證交所／櫃買中心開放資料抓最新清單；抓不到就用上次的快取或內建的小清單。"""
    stocks = {}
    sources = [(TWSE_URL, "Code", "Name", "上市"),
               (TPEX_URL, "SecuritiesCompanyCode", "CompanyName", "上櫃")]
    for url, kc, kn, market in sources:
        try:
            r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
            r.raise_for_status()
            for row in r.json():
                code = str(row.get(kc, "")).strip()
                name = str(row.get(kn, "")).strip()
                if CODE_OK.match(code) and name:
                    stocks[code] = {"name": name, "market": "ETF" if code.startswith("00") else market}
            print(f"[股票清單] {market}：累計 {len(stocks)} 檔")
        except Exception as e:  # noqa: BLE001
            print(f"[股票清單] 無法取得{market}清單：{e}")

    if len(stocks) > 500:
        with open(CACHE, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["code", "name", "market"])
            for code, info in sorted(stocks.items()):
                w.writerow([code, info["name"], info["market"]])
        return stocks
    if CACHE.exists():
        print("[股票清單] 改用上次儲存的清單")
        return _read_csv(CACHE)
    print("[股票清單] 改用內建精簡清單")
    return _read_csv(FALLBACK)


def load_aliases():
    path = DATA / "aliases.csv"
    out = {}
    if path.exists():
        with open(path, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r.get("alias") and r.get("code"):
                    out[r["alias"].strip()] = r["code"].strip()
    return out


class StockMatcher:
    """找出一段文字提到哪些股票，以及每次提到的位置（之後用來判斷多空）。"""

    # 代號後面接這些字，多半是價格、年份、數量，不是股票
    _NOT_CODE_AFTER = r"(?!\s*(?:年|元|塊|點|萬|億|張|股|月|天|人|名|件|次|分|/|-\d))"

    def __init__(self, stocks, aliases=None, ambiguous=()):
        self.stocks = stocks
        ambiguous = set(ambiguous)
        cjk_terms, ascii_terms = {}, {}
        for code, info in stocks.items():
            name = info["name"]
            if len(name) >= 2 and name not in ambiguous:
                cjk_terms[name] = code
        for alias, code in (aliases or {}).items():
            if code in stocks:
                (ascii_terms if alias.isascii() else cjk_terms)[alias] = code
        self.terms = {**cjk_terms, **ascii_terms}

        def alt(words):
            return "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True))

        self.cjk_re = re.compile(alt(cjk_terms)) if cjk_terms else None
        self.ascii_re = (re.compile(r"(?<![A-Za-z])(?:" + alt(ascii_terms) + r")(?![A-Za-z])")
                         if ascii_terms else None)
        self.code_re = re.compile(
            r"(?<![0-9A-Za-z.$])(00\d{3}[A-Z]?|\d{4})(?![0-9A-Za-z.%])" + self._NOT_CODE_AFTER)

    def find(self, text):
        """回傳 {代號: [(開始, 結束), ...]}"""
        hits = {}
        if not text:
            return hits
        for rx in (self.cjk_re, self.ascii_re):
            if rx is None:
                continue
            for m in rx.finditer(text):
                hits.setdefault(self.terms[m.group(0)], []).append(m.span())
        for m in self.code_re.finditer(text):
            code = m.group(1)
            if code in self.stocks:
                hits.setdefault(code, []).append(m.span(1))
        return hits

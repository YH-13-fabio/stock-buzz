"""技術指標：均線、RSI、KD、MACD（純 Python，不需額外套件）。

計算方式採台灣看盤軟體常用的版本：
- MA：簡單移動平均
- RSI(14)：Wilder 平滑
- KD(9,3,3)：RSV 以 1/3 權重平滑，初始值 50
- MACD(12,26,9)：DIF＝EMA12−EMA26，MACD＝DIF 的 EMA9，柱狀＝DIF−MACD
"""


def sma(xs, n):
    out, s = [], 0.0
    for i, x in enumerate(xs):
        s += x
        if i >= n:
            s -= xs[i - n]
        out.append(s / n if i >= n - 1 else None)
    return out


def ema(xs, n):
    k, out, prev = 2 / (n + 1), [], None
    for x in xs:
        prev = x if prev is None else prev + k * (x - prev)
        out.append(prev)
    return out


def rsi(closes, n=14):
    out = [None] * len(closes)
    if len(closes) <= n:
        return out
    gains = [max(0, closes[i] - closes[i - 1]) for i in range(1, len(closes))]
    losses = [max(0, closes[i - 1] - closes[i]) for i in range(1, len(closes))]
    ag, al = sum(gains[:n]) / n, sum(losses[:n]) / n
    for i in range(n, len(closes)):
        if i > n:
            ag = (ag * (n - 1) + gains[i - 1]) / n
            al = (al * (n - 1) + losses[i - 1]) / n
        out[i] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return out


def kd(highs, lows, closes, n=9):
    ks, ds, k, d = [], [], 50.0, 50.0
    for i in range(len(closes)):
        if i < n - 1:
            ks.append(None)
            ds.append(None)
            continue
        hh, ll = max(highs[i - n + 1:i + 1]), min(lows[i - n + 1:i + 1])
        rsv = 50.0 if hh == ll else (closes[i] - ll) / (hh - ll) * 100
        k = k * 2 / 3 + rsv / 3
        d = d * 2 / 3 + k / 3
        ks.append(k)
        ds.append(d)
    return ks, ds


def macd(closes, fast=12, slow=26, sig=9):
    dif = [a - b for a, b in zip(ema(closes, fast), ema(closes, slow))]
    dea = ema(dif, sig)
    return dif, dea, [a - b for a, b in zip(dif, dea)]


def _r(x, nd=2):
    return None if x is None else round(x, nd)


def summarize(bars):
    """bars: [(date, o, h, l, c, v), ...] 依日期排序。回傳給網頁用的摘要與最近 60 天序列。"""
    if len(bars) < 2:
        return None
    dates = [b[0] for b in bars]
    highs = [b[2] for b in bars]
    lows = [b[3] for b in bars]
    closes = [b[4] for b in bars]
    vols = [b[5] for b in bars]
    ma5, ma20, ma60 = sma(closes, 5), sma(closes, 20), sma(closes, 60)
    r = rsi(closes)
    k, d = kd(highs, lows, closes)
    dif, dea, hist = macd(closes)
    vma5 = sma(vols, 5)

    c, p = closes[-1], closes[-2]
    notes = []
    if ma5[-1] and ma20[-1] and ma60[-1]:
        if ma5[-1] > ma20[-1] > ma60[-1]:
            notes.append(("均線多頭排列", 1))
        elif ma5[-1] < ma20[-1] < ma60[-1]:
            notes.append(("均線空頭排列", -1))
    if ma20[-1] and ma20[-2]:
        if p <= ma20[-2] and c > ma20[-1]:
            notes.append(("站上月線", 1))
        elif p >= ma20[-2] and c < ma20[-1]:
            notes.append(("跌破月線", -1))
    if k[-1] is not None and k[-2] is not None:
        if k[-2] <= d[-2] and k[-1] > d[-1]:
            notes.append(("KD 黃金交叉", 1))
        elif k[-2] >= d[-2] and k[-1] < d[-1]:
            notes.append(("KD 死亡交叉", -1))
        if k[-1] > 80:
            notes.append(("KD 高檔", 0))
        elif k[-1] < 20:
            notes.append(("KD 低檔", 0))
    if r[-1] is not None:
        if r[-1] >= 70:
            notes.append(("RSI 過熱", 0))
        elif r[-1] <= 30:
            notes.append(("RSI 超賣", 0))
    if len(hist) > 1:
        if hist[-2] <= 0 < hist[-1]:
            notes.append(("MACD 翻紅", 1))
        elif hist[-2] >= 0 > hist[-1]:
            notes.append(("MACD 翻綠", -1))
    if vma5[-2] and vols[-1] > vma5[-2] * 2:
        notes.append(("爆量", 0))

    tail = slice(-60, None)
    return {
        "date": dates[-1],
        "close": _r(c), "chg": _r(c - p), "chg_pct": _r((c - p) / p * 100),
        "volume": vols[-1],
        "ma5": _r(ma5[-1]), "ma20": _r(ma20[-1]), "ma60": _r(ma60[-1]),
        "rsi": _r(r[-1], 1), "k": _r(k[-1], 1), "d": _r(d[-1], 1),
        "dif": _r(dif[-1]), "macd": _r(dea[-1]), "hist": _r(hist[-1]),
        "notes": notes,
        "series": {"d": dates[tail], "c": [_r(x) for x in closes[tail]],
                   "ma20": [_r(x) for x in ma20[tail]], "v": vols[tail]},
    }

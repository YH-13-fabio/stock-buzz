"""判斷「這則內容對某檔股票是看多、看空、還是中立」。

兩種模式：
1. 規則模式（免費）：看股票名稱前後 40 個字裡出現的多空關鍵字
2. Claude 模式（較準）：有設定 ANTHROPIC_API_KEY 時，請 Claude 判斷，失敗會自動退回規則模式
"""
import json
import os
import re

BULL = ["看多", "做多", "偏多", "多單", "看好", "看漲", "會漲", "噴", "起飛", "飆", "漲停", "大漲",
        "創新高", "新高", "突破", "利多", "買進", "加碼", "抄底", "低接", "進場", "上車", "歐印",
        "all in", "梭哈", "紅K", "長紅", "爆發", "續抱", "抱緊", "目標價", "賺爛", "發大財", "存股"]
BEAR = ["看空", "做空", "偏空", "空單", "放空", "看衰", "看跌", "會跌", "崩", "跌停", "大跌",
        "破底", "新低", "跌破", "利空", "賣出", "減碼", "停損", "認賠", "出場", "下車", "逃命",
        "倒貨", "出貨", "套牢", "被套", "住套房", "綠K", "長黑", "韭菜", "割肉", "畢業", "斷頭", "危險"]
NEG = ("不", "沒", "別", "勿", "非")
WINDOW = 40

_kw = sorted([(w, 1) for w in BULL] + [(w, -1) for w in BEAR], key=lambda x: -len(x[0]))
_KW_RE = re.compile("|".join(re.escape(w) for w, _ in _kw), re.IGNORECASE)
_KW_VAL = {w.lower(): v for w, v in _kw}


def score_text(text):
    """一段文字的多空分數（正=多、負=空）。關鍵字前面有「不/沒/別」會反轉。"""
    s = 0
    for m in _KW_RE.finditer(text):
        v = _KW_VAL[m.group(0).lower()]
        before = text[max(0, m.start() - 2):m.start()]
        if any(n in before for n in NEG):
            v = -v
        s += v
    return s


def _sign(x):
    return 1 if x > 0 else -1 if x < 0 else 0


_STOP = "。！？!?\n；;"


def _sentence(text, a, b):
    """取出提到股票的那一句（最多前後 WINDOW 個字），避免把別檔股票的多空算進來。"""
    lo = max(0, a - WINDOW)
    start = max((text.rfind(ch, lo, a) for ch in _STOP), default=-1)
    start = start + 1 if start >= 0 else lo
    hi = min(len(text), b + WINDOW)
    ends = [i for i in (text.find(ch, b, hi) for ch in _STOP) if i >= 0]
    return text[start:min(ends) if ends else hi]


def rule_sentiment(text, spans):
    """依股票每次被提到的那一句判斷多空。"""
    total = sum(score_text(_sentence(text, a, b)) for a, b in spans)
    return _sign(total)


def ptt_target_direction(title, text):
    """PTT [標的] 文有固定格式「分類：多/空」，直接採用。"""
    if "[標的]" not in title:
        return None
    m = re.search(r"分類\s*[:：]\s*(多|空|討論|心得)", text)
    if m:
        return {"多": 1, "空": -1}.get(m.group(1), 0)
    m = re.search(r"(多|空)\s*$", title.strip())
    if m:
        return 1 if m.group(1) == "多" else -1
    return None


class SentimentAnalyzer:
    def __init__(self, cfg, stocks):
        self.stocks = stocks
        self.model = cfg.get("model", "claude-haiku-5-5")
        self.budget = int(cfg.get("max_llm_calls_per_run", 400))
        self.client = None
        if cfg.get("use_llm_if_available", True) and os.environ.get("ANTHROPIC_API_KEY"):
            try:
                import anthropic
                self.client = anthropic.Anthropic()
                print(f"[多空判斷] 使用 Claude（{self.model}）")
            except Exception as e:  # noqa: BLE001
                print(f"[多空判斷] 無法使用 Claude，改用關鍵字規則：{e}")
        if self.client is None:
            print("[多空判斷] 使用關鍵字規則")
        self.mode = "llm" if self.client else "rules"

    def classify(self, title, text, hits):
        """回傳 {代號: 1/0/-1}；Claude 判斷「其實不是在講這檔股票」時，該代號會被拿掉。"""
        full = f"{title}\n{text}"
        result = {code: rule_sentiment(full, spans) for code, spans in hits.items()}
        forced = ptt_target_direction(title, text)
        if forced is not None:  # 套用到標題裡的那檔標的
            for code, spans in hits.items():
                if any(a < len(title) for a, _ in spans):
                    result[code] = forced

        if self.client and self.budget > 0:
            llm = self._llm(title, text, list(hits))
            if llm is not None:
                result = llm
        return result

    def _llm(self, title, text, codes):
        self.budget -= 1
        names = "、".join(f"{c} {self.stocks.get(c, {}).get('name', '')}" for c in codes)
        body = text[:2500]
        prompt = (
            "以下是一則台灣股市社群的貼文或影片字幕。請判斷作者對每一檔候選股票的態度。\n"
            f"候選股票：{names}\n\n"
            "規則：\n"
            "- bull = 看多／想買／認為會漲；bear = 看空／想賣／認為會跌；neutral = 只是提到、新聞陳述或看不出立場\n"
            "- 如果文中的字其實不是指這檔股票（例如是一般詞彙、年份、價格），標 not_stock\n"
            "- 只輸出 JSON，例如 {\"2330\": \"bull\", \"2317\": \"neutral\"}\n\n"
            f"標題：{title}\n內容：\n{body}"
        )
        try:
            resp = self.client.messages.create(
                model=self.model, max_tokens=300,
                messages=[{"role": "user", "content": prompt}])
            raw = "".join(getattr(b, "text", "") for b in resp.content)
            data = json.loads(re.search(r"\{.*\}", raw, re.S).group(0))
            mapping = {"bull": 1, "bear": -1, "neutral": 0}
            return {c: mapping[str(data.get(c, "neutral")).lower()]
                    for c in codes if str(data.get(c, "neutral")).lower() in mapping}
        except Exception as e:  # noqa: BLE001
            print(f"[多空判斷] Claude 判斷失敗，此篇改用規則：{e}")
            return None

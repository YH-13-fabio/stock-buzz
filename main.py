"""每日執行的主程式：爬文 → 辨識股票 → 判斷多空 → 存資料庫 → 產生 Dashboard 資料。

在自己電腦上執行：
    pip install -r requirements.txt
    python main.py
"""
import sys
from datetime import datetime
from pathlib import Path

import yaml

from buzz import TZ, dcard, ptt, site, youtube
from buzz.db import DB
from buzz.finmind import FinMind
from buzz.prices import PriceFetcher, target_codes
from buzz.sentiment import SentimentAnalyzer, rule_sentiment
from buzz.stocks import StockMatcher, load_aliases, load_stocks

ROOT = Path(__file__).resolve().parent


def main():
    cfg = yaml.safe_load(open(ROOT / "config.yaml", encoding="utf-8"))
    hours = cfg.get("lookback_hours", 30)
    max_per_post = cfg.get("max_stocks_per_post", 8)

    stocks = load_stocks()
    matcher = StockMatcher(stocks, load_aliases(), cfg.get("ambiguous_names", []))
    analyzer = SentimentAnalyzer(cfg.get("sentiment", {}), stocks)
    db = DB(ROOT / "data" / "buzz.db")

    items = []
    p = cfg.get("ptt", {})
    if p.get("enabled"):
        items += ptt.fetch(p.get("boards", ["Stock"]), hours, p.get("max_pages", 20))
    y = cfg.get("youtube", {})
    if y.get("enabled"):
        items += youtube.fetch(y.get("channels", []), y.get("lookback_hours", hours), y.get("max_videos_per_channel", 5))
    d = cfg.get("dcard", {})
    if d.get("enabled"):
        items += dcard.fetch(d.get("forums", ["stock"]), hours, d.get("limit", 60))

    fetched = datetime.now(TZ).isoformat(timespec="seconds")
    n_mentions = 0
    for item in items:
        db.save_item(item, fetched)
        hits = matcher.find(f"{item.title}\n{item.text}")
        sentiments = {}
        if 0 < len(hits) <= max_per_post:
            sentiments = analyzer.classify(item.title, item.text, hits)
        db.replace_mentions(item.id, item.date, item.source, sentiments)
        n_mentions += len(sentiments)

        if item.source == "ptt" and p.get("include_comments", True):
            c_mentions = {}
            for i, c in enumerate(item.comments):
                c_hits = matcher.find(c.text)
                if not c_hits or len(c_hits) > 3:
                    continue
                c_mentions[f"{item.id}#c{i}"] = {code: rule_sentiment(c.text, spans)
                                                 for code, spans in c_hits.items()}
            for cid, s in c_mentions.items():
                db.add_mentions(cid, item.date, "ptt_comment", s)
                n_mentions += len(s)
    db.commit()
    print(f"[完成] 共處理 {len(items)} 則內容、{n_mentions} 筆股票提及（多空判斷：{analyzer.mode}）")

    pr = cfg.get("prices", {})
    if pr.get("enabled", True):
        codes = target_codes(db, 7, pr.get("max_stocks", 80))
        # 有 FinMind 就用它的官方日 K（歷史長、免費）；沒有才用永豐 1 分 K 合成
        if not FinMind(db, pr).update(codes):
            PriceFetcher(db, pr).update(codes)

    site.build(db, stocks, ROOT / "docs" / "data.json")


if __name__ == "__main__":
    sys.exit(main())

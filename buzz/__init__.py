"""股市討論熱度：爬文、辨識股票、判斷多空。"""
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Taipei")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")


@dataclass
class Comment:
    tag: str          # 推 / 噓 / →
    user: str
    text: str


@dataclass
class Item:
    """一則內容：一篇文章、一部影片。"""
    id: str
    source: str               # ptt / youtube / dcard
    kind: str                 # post / video
    url: str
    title: str
    author: str
    published: datetime       # 有時區的時間
    text: str
    comments: list = field(default_factory=list)

    @property
    def date(self) -> str:
        return self.published.astimezone(TZ).strftime("%Y-%m-%d")

"""YouTube：用官方 API 找頻道最新影片，再抓字幕來分析。

注意：YouTube 有時會擋掉雲端主機（包含 GitHub Actions）抓字幕，
抓不到字幕時會改用「標題＋影片說明」分析，資訊較少但仍可運作。
"""
import os
import re
from datetime import datetime, timedelta

import requests

from . import TZ, Item

API = "https://www.googleapis.com/youtube/v3"


def _get(path, key, **params):
    r = requests.get(f"{API}/{path}", params={**params, "key": key}, timeout=20)
    r.raise_for_status()
    return r.json()


def _uploads_playlist(channel, key):
    channel = channel.strip()
    m = re.search(r"youtube\.com/(?:channel/(UC[\w-]+)|(@[\w.\-]+))", channel)
    if m:
        channel = m.group(1) or m.group(2)
    if channel.startswith("UC"):
        data = _get("channels", key, part="contentDetails,snippet", id=channel)
    else:
        handle = channel if channel.startswith("@") else "@" + channel
        data = _get("channels", key, part="contentDetails,snippet", forHandle=handle)
    items = data.get("items") or []
    if not items:
        return None, None
    it = items[0]
    return it["contentDetails"]["relatedPlaylists"]["uploads"], it["snippet"]["title"]


def _seconds(iso):
    """ISO 8601 影片長度（例如 PT12M3S）→ 秒數。"""
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return None
    d, h, mi, se = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + se


def _durations(ids, key):
    if not ids:
        return {}
    data = _get("videos", key, part="contentDetails,snippet", id=",".join(ids))
    return {v["id"]: (_seconds(v["contentDetails"].get("duration")),
                      v["snippet"].get("liveBroadcastContent", "none"))
            for v in data.get("items", [])}


def _transcript(video_id):
    # 只抓中文字幕。部分中文影片只有「英文自動字幕」，那是 YouTube 把中文誤認成英文，內容是亂碼，不採用
    langs = ["zh-TW", "zh-Hant", "zh", "zh-HK", "zh-Hans", "zh-CN"]
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        if hasattr(YouTubeTranscriptApi, "get_transcript"):  # 舊版
            parts = YouTubeTranscriptApi.get_transcript(video_id, languages=langs)
            return "".join(p["text"] for p in parts)
        fetched = YouTubeTranscriptApi().fetch(video_id, languages=langs)  # 新版
        return "".join(s.text for s in fetched)
    except Exception as e:  # noqa: BLE001
        why = {"TranscriptsDisabled": "影片沒有字幕軌，常見於字幕直接燒在畫面上的短影音",
               "NoTranscriptFound": "沒有中文字幕"}.get(type(e).__name__, type(e).__name__)
        print(f"[YouTube] {video_id} 無法取得字幕，改用標題與說明（{why}）")
        return ""


def fetch(channels, lookback_hours=30, max_videos=5, short_max=180):
    key = os.environ.get("YOUTUBE_API_KEY")
    if not key:
        print("[YouTube] 沒有設定 YOUTUBE_API_KEY，略過 YouTube")
        return []
    cutoff = datetime.now(TZ) - timedelta(hours=lookback_hours)
    items = []
    for ch in channels:
        try:
            playlist, ch_title = _uploads_playlist(ch, key)
            if not playlist:
                print(f"[YouTube] 找不到頻道：{ch}")
                continue
            data = _get("playlistItems", key, part="snippet,contentDetails",
                        playlistId=playlist, maxResults=min(50, max_videos * 3 + 5))  # 多抓一些，扣掉 Shorts 後還夠
        except Exception as e:  # noqa: BLE001
            print(f"[YouTube] 讀取頻道 {ch} 失敗：{e}")
            continue
        recent = []
        for v in data.get("items", []):
            published = datetime.fromisoformat(
                v["contentDetails"].get("videoPublishedAt", v["snippet"]["publishedAt"]).replace("Z", "+00:00"))
            if published >= cutoff:
                recent.append((v, published))
        try:
            info = _durations([v["contentDetails"]["videoId"] for v, _ in recent], key)
        except Exception as e:  # noqa: BLE001
            print(f"[YouTube] 讀取影片長度失敗：{e}")
            info = {}
        n = skipped = 0
        for v, published in recent:
            sn = v["snippet"]
            vid = v["contentDetails"]["videoId"]
            secs, live = info.get(vid, (None, "none"))
            # 不抓 Shorts（3 分鐘以內）和還沒開始／正在直播的影片
            if live in ("upcoming", "live") or (secs is not None and secs <= short_max) \
                    or "#shorts" in (sn["title"] + sn.get("description", "")).lower():
                skipped += 1
                continue
            if n >= max_videos:
                break
            text = sn.get("description", "") + "\n" + _transcript(vid)
            items.append(Item(id=f"yt:{vid}", source="youtube", kind="video",
                              url=f"https://www.youtube.com/watch?v={vid}", title=sn["title"],
                              author=ch_title, published=published, text=text))
            n += 1
        extra = f"（略過 {skipped} 部短影音／直播）" if skipped else ""
        print(f"[YouTube] {ch_title}：取得 {n} 部新影片{extra}")
    return items

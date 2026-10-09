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


def _transcript(video_id):
    langs = ["zh-TW", "zh-Hant", "zh", "zh-Hans", "en"]
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        if hasattr(YouTubeTranscriptApi, "get_transcript"):  # 舊版
            parts = YouTubeTranscriptApi.get_transcript(video_id, languages=langs)
            return "".join(p["text"] for p in parts)
        fetched = YouTubeTranscriptApi().fetch(video_id, languages=langs)  # 新版
        return "".join(s.text for s in fetched)
    except Exception as e:  # noqa: BLE001
        print(f"[YouTube] {video_id} 無法取得字幕（改用標題與說明）：{type(e).__name__}")
        return ""


def fetch(channels, lookback_hours=30, max_videos=5):
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
                        playlistId=playlist, maxResults=max_videos)
        except Exception as e:  # noqa: BLE001
            print(f"[YouTube] 讀取頻道 {ch} 失敗：{e}")
            continue
        n = 0
        for v in data.get("items", []):
            sn = v["snippet"]
            vid = v["contentDetails"]["videoId"]
            published = datetime.fromisoformat(
                v["contentDetails"].get("videoPublishedAt", sn["publishedAt"]).replace("Z", "+00:00"))
            if published < cutoff:
                continue
            text = sn.get("description", "") + "\n" + _transcript(vid)
            items.append(Item(id=f"yt:{vid}", source="youtube", kind="video",
                              url=f"https://www.youtube.com/watch?v={vid}", title=sn["title"],
                              author=ch_title, published=published, text=text))
            n += 1
        print(f"[YouTube] {ch_title}：取得 {n} 部新影片")
    return items

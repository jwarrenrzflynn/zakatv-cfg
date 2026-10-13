#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import re
import json
import urllib.parse
from urllib.parse import quote
from typing import Dict, List, Any

try:
    from base.spider import Spider as SpiderBase
except ImportError:
    class SpiderBase:
        pass

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    import urllib.request
    HAS_REQUESTS = False

def format_remarks(brand="ZakaTV", meta=""):
    clean_meta = str(meta or "").strip()
    clean_meta = re.sub(r"[\r\n\t]+", " ", clean_meta).strip()
    if clean_meta:
        return "%s | %s" % (brand, clean_meta)
    return brand

class Spider(SpiderBase):
    siteUrl = "https://mdcmai4.xyz"
    api_categories = "/api/v1/categories"
    api_videos = "/api/v1/videos"
    api_short_dramas = "/api/v1/short-dramas"
    api_short_drama_detail = "/api/v1/short-dramas/{id}?productId=1"
    api_search = "/api/v1/videos/search"
    api_m3u8_proxy = "/api/v1/m3u8/proxy?path="
    api_img_proxy = "/api/v1/image/proxy?path="

    SHORT_DRAMA_TID = "short_drama_ai"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Referer": "https://mdcmai4.xyz/",
        "Origin": "https://mdcmai4.xyz",
        "Accept": "application/json, text/plain, */*",
    }

    brandActor = "📺TG群: https://t.me/+3t5XRPPo9mlkZDRl"
    brandDirector = "📺ZakaTV"
    tgGroup = "https://t.me/+3t5XRPPo9mlkZDRl"

    def getName(self) -> str:
        return "麻豆短剧·ZakaTV"

    def init(self, extend: str = "") -> bool:
        return True

    def isVideoFormat(self, url: str) -> bool:
        low = (url or "").lower()
        return any(k in low for k in (".m3u8", ".mp4", ".flv", ".webm", ".ts"))

    def manualVideoCheck(self) -> bool:
        return False

    def destroy(self):
        pass

    def _fetch_json(self, url: str) -> Dict[str, Any]:
        try:
            if HAS_REQUESTS:
                resp = requests.get(url, headers=self.headers, timeout=10)
                if resp.status_code == 200:
                    return resp.json()
            else:
                req = urllib.request.Request(url, headers=self.headers)
                with urllib.request.urlopen(req, timeout=10) as response:
                    return json.loads(response.read().decode("utf-8"))
        except Exception:
            pass
        return {}

    def _format_cover(self, cover_path: str) -> str:
        if not cover_path:
            return ""
        if cover_path.startswith("http"):
            return cover_path
        if cover_path.startswith("/uploads/") or cover_path.startswith("/api/"):
            return "%s%s" % (self.siteUrl, cover_path)
        encoded_path = urllib.parse.quote(cover_path, safe="")
        return "%s%s%s" % (self.siteUrl, self.api_img_proxy, encoded_path)

    def _format_play_url(self, video_path: str) -> str:
        if not video_path:
            return ""
        if video_path.startswith("http"):
            return video_path
        if video_path.startswith("/api/v1/m3u8/proxy"):
            return "%s%s" % (self.siteUrl, video_path)
        encoded_path = urllib.parse.quote(video_path, safe="")
        return "%s%s%s" % (self.siteUrl, self.api_m3u8_proxy, encoded_path)

    def _format_duration(self, seconds: int) -> str:
        if not seconds:
            return ""
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        if h > 0:
            return "%02d:%02d:%02d" % (h, m, s)
        return "%02d:%02d" % (m, s)

    def homeContent(self, filter: bool = False) -> Dict[str, Any]:
        classes = [
            {"type_id": self.SHORT_DRAMA_TID, "type_name": "🔥 AI短剧"}
        ]

        url = "%s%s" % (self.siteUrl, self.api_categories)
        res = self._fetch_json(url)

        if res.get("code") == 200 and isinstance(res.get("data"), list):
            for cat in res["data"]:
                cat_name = str(cat.get("name", "")).strip()
                if "交友闲谈" in cat_name:
                    continue
                if cat.get("enabled", True):
                    classes.append({
                        "type_id": str(cat.get("id")),
                        "type_name": cat_name or "未知分类"
                    })

        result = {"class": classes}

        if filter:
            filters = {}

            filters[self.SHORT_DRAMA_TID] = [{
                "key": "sort",
                "name": "排序",
                "value": [
                    {"n": "热门短剧", "v": "heat"},
                    {"n": "最新短剧", "v": "latest"}
                ]
            }]

            video_filter = [{
                "key": "sort",
                "name": "排序",
                "value": [
                    {"n": "热门推荐", "v": "heat"},
                    {"n": "最新发布", "v": "latest"},
                    {"n": "最多播放", "v": "views"},
                    {"n": "最高评分", "v": "rating"}
                ]
            }]

            for item in classes:
                tid = item["type_id"]
                if tid != self.SHORT_DRAMA_TID:
                    filters[tid] = video_filter

            result["filters"] = filters

        return result

    def categoryContent(self, tid: str, pg: str, filter: bool, extend: Dict) -> Dict[str, Any]:
        page = int(pg) if pg else 1
        videos = []
        pagecount = page
        total = 0
        extend = extend or {}

        if str(tid) == self.SHORT_DRAMA_TID:
            sort_val = extend.get("sort") or "heat"
            if sort_val not in ("heat", "latest"):
                sort_val = "heat"

            url = "%s%s?productId=1&sortBy=%s&page=%d&size=12" % (self.siteUrl, self.api_short_dramas, sort_val, page)
            res = self._fetch_json(url)
            if res.get("code") == 200:
                data = res.get("data", {})
                pagecount = data.get("totalPages", page)
                total = data.get("total", 0)

                for item in data.get("items", []):
                    ep_cnt = item.get("episodeCount", 1)
                    meta_desc = "全%s集" % ep_cnt
                    remarks = format_remarks("ZakaTV", meta_desc)
                    videos.append({
                        "vod_id": "drama@@%s@@%s@@%s" % (item.get("id"), item.get("title", ""), item.get("coverUrl", "")),
                        "vod_name": item.get("title", ""),
                        "vod_pic": self._format_cover(item.get("coverUrl", "")),
                        "vod_remarks": remarks,
                        "style": {"type": "rect", "ratio": 0.75}
                    })
        else:
            sort_val = extend.get("sort") or "heat"
            if sort_val not in ("heat", "latest", "views", "rating"):
                sort_val = "heat"

            url = "%s%s?page=%d&size=24&categoryId=%s&sortBy=%s" % (self.siteUrl, self.api_videos, page, tid, sort_val)
            res = self._fetch_json(url)
            if res.get("code") == 200:
                data = res.get("data", {})
                pagecount = data.get("totalPages", page)
                total = data.get("total", 0)

                for item in data.get("items", []):
                    v_url = item.get("videoUrl", "")
                    meta_desc = self._format_duration(item.get("durationSec", 0)) or item.get("categoryName", "")
                    remarks = format_remarks("ZakaTV", meta_desc)
                    videos.append({
                        "vod_id": "video@@%s@@%s@@%s@@%s" % (item.get("id"), v_url, item.get("title", ""), item.get("coverUrl", "")),
                        "vod_name": item.get("title", ""),
                        "vod_pic": self._format_cover(item.get("coverUrl", "")),
                        "vod_remarks": remarks,
                        "style": {"type": "rect", "ratio": 1.78}
                    })

        return {
            "list": videos,
            "page": page,
            "pagecount": pagecount,
            "limit": 12 if str(tid) == self.SHORT_DRAMA_TID else 24,
            "total": total
        }

    def detailContent(self, ids: List[str]) -> Dict[str, Any]:
        vod_id = ids[0]

        if "@@" in vod_id:
            parts = vod_id.split("@@")
            vtype = parts[0]

            if vtype == "drama":
                drama_id = parts[1]
                title = parts[2] if len(parts) > 2 else "短剧详情"
                cover = parts[3] if len(parts) > 3 else ""

                detail_url = "%s%s" % (self.siteUrl, self.api_short_drama_detail.format(id=drama_id))
                res = self._fetch_json(detail_url)

                episodes = []
                remarks = "ZakaTV · 短剧"
                if res.get("code") == 200 and isinstance(res.get("data"), dict):
                    drama_data = res["data"]
                    title = drama_data.get("title", title)
                    cover = drama_data.get("coverUrl", cover)
                    ep_total = drama_data.get("episodeCount")
                    if ep_total:
                        remarks = format_remarks("ZakaTV", "全%s集" % ep_total)

                    for ep in drama_data.get("episodes", []):
                        ep_no = ep.get("episodeNo", 1)
                        ep_title = "第%d集" % ep_no
                        raw_vurl = ep.get("videoUrl", "")
                        if raw_vurl:
                            play_stream = self._format_play_url(raw_vurl)
                            episodes.append("%s$%s" % (ep_title, play_stream))

                play_url_str = "#".join(episodes) if episodes else "暂无分集数据$error"
                from_name = "AI短剧专线"

            else:
                video_url = parts[2] if len(parts) > 2 else ""
                title = parts[3] if len(parts) > 3 else "视频详情"
                cover = parts[4] if len(parts) > 4 else ""
                play_stream = self._format_play_url(video_url)
                play_url_str = "正片$%s" % play_stream if play_stream else "暂无播放地址$error"
                from_name = "Zaka专线"
                remarks = format_remarks("ZakaTV", "高清正片")
        else:
            title = "在线播放"
            cover = ""
            from_name = "Zaka专线"
            play_url_str = "暂无播放地址$error"
            remarks = "ZakaTV"

        full_desc = (
            "【🔥 官方交流群: %s】\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Zaka专线 极速硬解"
        ) % self.tgGroup

        return {
            "list": [{
                "vod_id": vod_id,
                "vod_name": title,
                "vod_pic": self._format_cover(cover),
                "vod_actor": self.brandActor,
                "vod_director": self.brandDirector,
                "vod_remarks": remarks,
                "vod_content": full_desc,
                "vod_play_from": from_name,
                "vod_play_url": play_url_str
            }]
        }

    def searchContent(self, key: str, quick: str, pg="1") -> Dict[str, Any]:
        page = int(pg) if pg else 1
        encoded_kw = urllib.parse.quote(key)
        url = "%s%s?page=%d&size=24&q=%s" % (self.siteUrl, self.api_search, page, encoded_kw)
        res = self._fetch_json(url)

        videos = []
        if res.get("code") == 200:
            data = res.get("data", {})
            for item in data.get("items", []):
                v_url = item.get("videoUrl", "")
                meta_desc = self._format_duration(item.get("durationSec", 0)) or item.get("categoryName", "")
                remarks = format_remarks("ZakaTV", meta_desc)
                videos.append({
                    "vod_id": "video@@%s@@%s@@%s@@%s" % (item.get("id"), v_url, item.get("title", ""), item.get("coverUrl", "")),
                    "vod_name": item.get("title", ""),
                    "vod_pic": self._format_cover(item.get("coverUrl", "")),
                    "vod_remarks": remarks,
                    "style": {"type": "rect", "ratio": 1.78}
                })

        return {"list": videos}

    def playerContent(self, flag: str, id: str, vipFlags: str) -> Dict[str, Any]:
        return {
            "parse": 0,
            "playUrl": "",
            "url": id,
            "header": {
                "User-Agent": self.headers["User-Agent"],
                "Referer": "https://mdcmai4.xyz/",
                "Origin": "https://mdcmai4.xyz"
            }
        }

    def localProxy(self, param: Dict) -> List[Any]:
        return [404, "text/plain", ""]

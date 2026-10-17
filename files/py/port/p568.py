# -*- coding: utf-8 -*-
import json
import ssl
import time
import urllib.parse
import urllib.request

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        pass

RECT_178_STYLE = {"type": "rect", "ratio": 1.78}

CLASSES_CACHE = [
    {"type_id": "1", "type_name": "精品推荐"},
    {"type_id": "2", "type_name": "国产色情"},
    {"type_id": "3", "type_name": "主播直播"},
    {"type_id": "4", "type_name": "亚洲无码"},
    {"type_id": "5", "type_name": "亚洲有码"},
    {"type_id": "6", "type_name": "中文字幕"},
    {"type_id": "7", "type_name": "巨乳美乳"},
    {"type_id": "8", "type_name": "人妻熟女"},
    {"type_id": "9", "type_name": "强奸乱伦"},
    {"type_id": "10", "type_name": "欧美精品"},
    {"type_id": "11", "type_name": "萝莉少女"},
    {"type_id": "12", "type_name": "伦理三级"},
    {"type_id": "13", "type_name": "成人动漫"},
    {"type_id": "14", "type_name": "自拍偷拍"},
    {"type_id": "15", "type_name": "制服丝袜"},
    {"type_id": "16", "type_name": "口交颜射"},
    {"type_id": "17", "type_name": "日本精品"},
    {"type_id": "18", "type_name": "cosplay"},
    {"type_id": "19", "type_name": "素人自拍"},
    {"type_id": "20", "type_name": "台湾辣妹"},
    {"type_id": "21", "type_name": "韩国御姐"},
    {"type_id": "22", "type_name": "唯美港姐"},
    {"type_id": "23", "type_name": "东南亚av"}
]

class Spider(BaseSpider):
    def __init__(self):
        super(Spider, self).__init__()
        self.api_base = "https://api.sgapiaba.xyz"
        self.web_base = "https://rand.sgh5005.xyz"
        self.app_version = "5.4.5"

    def init(self, extend=""):
        pass

    def homeContent(self, filter):
        return {
            "class": CLASSES_CACHE,
            "filters": {},
            "style": RECT_178_STYLE
        }

    def homeVideoContent(self):
        return self.categoryContent("1", "1", {}, {})

    def _fetch_url(self, url, headers=None, timeout=8):
        req_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Referer": "%s/" % self.web_base,
            "Origin": self.web_base,
            "Accept": "application/json, text/plain, */*",
            "version": self.app_version
        }
        if headers:
            req_headers.update(headers)
        
        ctx = ssl._create_unverified_context()
        req = urllib.request.Request(url, headers=req_headers)
        start_t = time.time()
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                elapsed_ms = int((time.time() - start_t) * 1000)
                code = resp.getcode()
                raw = resp.read()
                charset = resp.headers.get_content_charset() or "utf-8"
                text = raw.decode(charset, errors="ignore")
                return {
                    "status_code": code,
                    "elapsed_ms": elapsed_ms,
                    "headers": dict(resp.headers),
                    "body": text,
                    "error": ""
                }
        except Exception as e:
            return {
                "status_code": 0,
                "elapsed_ms": int((time.time() - start_t) * 1000),
                "headers": {},
                "body": "",
                "error": str(e)
            }

    def _parse_card_list(self, data_list):
        cards = []
        for item in data_list:
            vid = str(item.get("id", ""))
            title = str(item.get("title", item.get("name", "")))
            pic = str(item.get("cover", item.get("coverbase64", {}).get("url", "")))
            playtimes = item.get("playtimes", "")
            if playtimes:
                remarks = "ZakaTV | %s" % playtimes
            else:
                views = item.get("pageviews", "")
                remarks = ("ZakaTV · %s次播放" % views) if views else "ZakaTV"
            cards.append({
                "vod_id": vid,
                "vod_name": title,
                "vod_pic": pic,
                "vod_remarks": remarks,
                "style": RECT_178_STYLE
            })
        return cards

    def categoryContent(self, tid, pg, filter, extend):
        page_num = str(pg or "1")
        target_url = "%s/api/videosort/%s?page=%s" % (self.api_base, tid, page_num)
        res = self._fetch_url(target_url, timeout=8)
        cards = []
        pagecount = 1
        total = 0

        if res["status_code"] == 200 and res["body"]:
            try:
                js = json.loads(res["body"])
                rescont = js.get("rescont", {})
                if isinstance(rescont, dict):
                    cards = self._parse_card_list(rescont.get("data", []))
                    pagecount = int(rescont.get("last_page", 1))
                    total = int(rescont.get("total", 0))
                elif isinstance(rescont, list):
                    cards = self._parse_card_list(rescont)
                    pagecount = 10
                    total = len(cards) * 10
            except Exception:
                pass

        return {
            "page": int(page_num),
            "pagecount": pagecount,
            "limit": len(cards),
            "total": total,
            "list": cards,
            "style": RECT_178_STYLE
        }

    def detailContent(self, ids):
        vid = str(ids[0]) if isinstance(ids, list) else str(ids)
        target_url = "%s/api/videoplay/%s" % (self.api_base, vid)
        res = self._fetch_url(target_url, timeout=8)

        vod_title = "视频详情"
        vod_pic = ""
        vod_content = "📺TG群: https://t.me/+3t5XRPPo9mlkZDRl\nZakaTV 官方正版接口"
        play_url = ""

        if res["status_code"] == 200 and res["body"]:
            try:
                js = json.loads(res["body"])
                rescont = js.get("rescont", {})
                if isinstance(rescont, dict):
                    vod_title = str(rescont.get("title", rescont.get("name", vod_title)))
                    vod_pic = str(rescont.get("cover", rescont.get("coverbase64", {}).get("url", "")))
                    play_url = str(rescont.get("videopath", rescont.get("video_url", rescont.get("url", ""))))
            except Exception:
                pass

        play_url_val = play_url if play_url else vid
        play_url_str = "正片$%s" % play_url_val

        vod = {
            "vod_id": vid,
            "vod_name": vod_title,
            "vod_pic": vod_pic,
            "type_name": "Zaka专线",
            "vod_year": "2026",
            "vod_area": "亚洲",
            "vod_remarks": "ZakaTV",
            "vod_actor": "📺TG群: https://t.me/+3t5XRPPo9mlkZDRl",
            "vod_director": "📺ZakaTV",
            "vod_content": vod_content,
            "vod_play_from": "Zaka专线",
            "vod_play_url": play_url_str
        }

        return {"list": [vod]}

    def playerContent(self, flag, id, vipFlags):
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Referer": "%s/" % self.web_base,
            "Origin": self.web_base
        }
        if id.startswith("http"):
            return {
                "parse": 0,
                "playUrl": "",
                "url": id,
                "header": headers
            }
        
        target_url = "%s/api/videoplay/%s" % (self.api_base, id)
        res = self._fetch_url(target_url, timeout=6)
        real_url = ""
        if res["status_code"] == 200 and res["body"]:
            try:
                js = json.loads(res["body"])
                rescont = js.get("rescont", {})
                real_url = str(rescont.get("videopath", rescont.get("video_url", "")))
            except Exception:
                pass

        return {
            "parse": 0,
            "playUrl": "",
            "url": real_url,
            "header": headers
        }

    def searchContent(self, key, quick, pg="1"):
        page_num = str(pg or "1")
        encoded_key = urllib.parse.quote(str(key))
        target_url = "%s/api/v4/search?key=%s&page=%s" % (self.api_base, encoded_key, page_num)
        res = self._fetch_url(target_url, timeout=8)
        cards = []
        pagecount = 1
        total = 0

        if res["status_code"] == 200 and res["body"]:
            try:
                js = json.loads(res["body"])
                rescont = js.get("rescont", {})
                if isinstance(rescont, dict):
                    cards = self._parse_card_list(rescont.get("data", []))
                    pagecount = int(rescont.get("last_page", 1))
                    total = int(rescont.get("total", 0))
            except Exception:
                pass

        return {
            "page": int(page_num),
            "pagecount": pagecount,
            "limit": len(cards),
            "total": total,
            "list": cards,
            "style": RECT_178_STYLE
        }

    def action(self, action):
        return ""

    def liveContent(self):
        return ""

    def localProxy(self, params):
        return [200, "text/plain", "OK"]

    def manualVideoCheck(self):
        return False

    def isVideoFormat(self, url):
        return False

    def destroy(self):
        pass
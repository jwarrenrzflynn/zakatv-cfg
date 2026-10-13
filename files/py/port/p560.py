# -*- coding: utf-8 -*-
import json
import urllib.request
import urllib.error
import urllib.parse
import ssl
import re
from html import unescape

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        pass

class Spider(BaseSpider):

    def __init__(self):
        self.site_url = "https://app-1.mmnnxx.shop"
        self.default_headers = {
            "User-Agent": "Mozilla/5.0 (Linux; Android 12; SM-G975F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": "https://app-1.mmnnxx.shop/",
            "Connection": "keep-alive"
        }
        self.sort_options = [
            {"n": "默认排序", "v": ""},
            {"n": "最新点播", "v": "db"},
            {"n": "播放时长", "v": "bs"},
            {"n": "最多点击", "v": "h"},
            {"n": "最多弹幕", "v": "d"},
            {"n": "最多评论", "v": "p"},
            {"n": "最多收藏", "v": "s"},
            {"n": "最多点赞", "v": "z"}
        ]

    def init(self, extend=""):
        pass

    def homeContent(self, filter):
        categories = [
            ("latest", "最新视频"),
            ("日韩无码", "日韩无码"),
            ("国产精品", "国产精品"),
            ("中文字幕", "中文字幕"),
            ("国产传媒", "国产传媒"),
            ("日韩精品", "日韩精品"),
            ("精品探花", "精品探花"),
            ("制服诱惑", "制服诱惑"),
            ("人妻系列", "人妻系列"),
            ("自拍偷拍", "自拍偷拍"),
            ("强奸乱伦", "强奸乱伦"),
            ("欧美精品", "欧美精品"),
            ("黑料网曝", "黑料网曝"),
            ("动漫精品", "动漫精品"),
            ("反差母狗", "反差母狗"),
            ("颜值正义", "颜值正义"),
            ("熟女少妇", "熟女少妇"),
            ("大秀视频", "大秀视频"),
            ("明星换脸", "明星换脸"),
            ("巨乳系列", "巨乳系列"),
            ("颜射系列", "颜射系列"),
            ("口交视频", "口交视频"),
            ("自慰系列", "自慰系列"),
            ("教师学生", "教师学生"),
            ("AV明星", "AV明星"),
            ("SM重味", "SM重味"),
            ("人兽乱交", "人兽乱交"),
            ("伦理影片", "伦理影片"),
            ("AV解说", "AV解说"),
            ("pornstars_zone", "明星专区"),
            ("categories_zone", "类型总览")
        ]

        classes = []
        filters = {}

        for tid, tname in categories:
            classes.append({"type_id": tid, "type_name": tname})
            filters[tid] = [
                {
                    "key": "rq",
                    "name": "排序",
                    "value": self.sort_options
                }
            ]

        return {
            "class": classes,
            "filters": filters
        }

    def homeVideoContent(self):
        return {"list": []}

    def _fetch(self, path, referer=None):
        url = self.site_url + path if path.startswith("/") else (path if path.startswith("http") else self.site_url + "/" + path)
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        
        headers = dict(self.default_headers)
        if referer:
            headers["Referer"] = referer

        req = urllib.request.Request(url, headers=headers)
        try:
            res = urllib.request.urlopen(req, context=ctx, timeout=15)
            raw = res.read()
            try:
                return raw.decode("utf-8")
            except Exception:
                return raw.decode("gbk", errors="ignore")
        except Exception:
            return ""

    def _parse_card_list(self, html):
        vod_list = []
        thumb_blocks = re.findall(r'<div class="thumb">([\s\S]*?)</div>\s*</div>', html)
        if not thumb_blocks:
            thumb_blocks = re.findall(r'<div class="thumb">([\s\S]*?)(?=<div class="thumb">|$)', html)

        for block in thumb_blocks:
            id_match = re.search(r'href=[\'"][^\'"]*?\?play-([0-9]+)-', block)
            if not id_match:
                continue
            cid = id_match.group(1)

            title_match = re.search(r'alt=[\'"]([^\'"]+)[\'"]', block)
            if not title_match:
                title_match = re.search(r'<div class="thumb-info">([^<]+)</div>', block)
            vod_name = unescape(title_match.group(1)).strip() if title_match else "未命名影片"

            pic_match = re.search(r'<img[^>]+?src=[\'"](https?://[^\'"]+)[\'"]', block)
            vod_pic = pic_match.group(1).strip() if pic_match else ""

            duration_match = re.search(r'<div class="icon-top-right">[\s\S]*?&nbsp;([^<]+)</div>', block)
            duration = duration_match.group(1).strip() if duration_match else ""

            remarks = "ZakaTV | %s" % duration if duration else "ZakaTV"
            raw_id = "%s|%s" % (cid, vod_pic)

            vod_list.append({
                "vod_id": raw_id,
                "vod_name": vod_name,
                "vod_pic": vod_pic,
                "vod_remarks": remarks,
                "style": {"type": "rect", "ratio": 1.78}
            })

        return vod_list

    def _parse_folder_list(self, html, mode="star"):
        folder_list = []
        seen = set()

        if mode == "star":
            items = re.findall(r'<a\b[^>]*?href=[\'"][^\'"]*?\?pornstar=([^"\'&]+)[^\'"]*[\'"][^>]*>([\s\S]*?)</a>', html)
            for raw_val, inner in items:
                name = unescape(raw_val).strip()
                if not name or name in seen or name.isdigit():
                    continue
                seen.add(name)

                pic_match = re.search(r'<img[^>]+?src=[\'"](https?://[^\'"]+)[\'"]', inner)
                pic = pic_match.group(1).strip() if pic_match else ""

                clean_name = re.sub(r'<[^>]+>', '', inner).strip() or name

                folder_list.append({
                    "vod_id": "star_" + name,
                    "vod_name": clean_name,
                    "vod_pic": pic,
                    "vod_tag": "folder",
                    "vod_remarks": "ZakaTV · 女优",
                    "style": {"type": "rect", "ratio": 1.78}
                })
        else:
            items = re.findall(r'<a\b[^>]*?href=[\'"][^\'"]*?\?fenlei=([^"\'&]+)[^\'"]*[\'"][^>]*>([\s\S]*?)</a>', html)
            for raw_val, inner in items:
                name = unescape(raw_val).strip()
                if not name or name in seen or name.isdigit() or name in ["首页", "最新", "类型"]:
                    continue
                seen.add(name)

                pic_match = re.search(r'<img[^>]+?src=[\'"](https?://[^\'"]+)[\'"]', inner)
                pic = pic_match.group(1).strip() if pic_match else ""

                clean_name = re.sub(r'<[^>]+>', '', inner).strip() or name

                folder_list.append({
                    "vod_id": "cat_" + name,
                    "vod_name": clean_name,
                    "vod_pic": pic,
                    "vod_tag": "folder",
                    "vod_remarks": "ZakaTV · 分类",
                    "style": {"type": "rect", "ratio": 1.78}
                })

        return folder_list

    def categoryContent(self, tid, pg, filter, extend):
        try:
            page = int(pg) if pg else 1
            ext = extend or {}
            rq = ext.get("rq", "")
            rq_param = ("&rq=%s" % rq) if rq else ""

            if tid == "latest":
                path = "/?video=%d.html%s" % (page, rq_param)
                html = self._fetch(path)
                cards = self._parse_card_list(html)
            elif tid == "pornstars_zone":
                path = "/?pornstars=md&p=%d" % page
                html = self._fetch(path)
                cards = self._parse_folder_list(html, mode="star")
            elif tid == "categories_zone":
                path = "/?categories=%d.html" % page
                html = self._fetch(path)
                cards = self._parse_folder_list(html, mode="cat")
            elif tid.startswith("star_"):
                star_name = urllib.parse.quote(tid.replace("star_", ""))
                path = "/?pornstar=%s&p=%d%s" % (star_name, page, rq_param)
                html = self._fetch(path)
                cards = self._parse_card_list(html)
            elif tid.startswith("cat_"):
                cat_name = urllib.parse.quote(tid.replace("cat_", ""))
                path = "/?fenlei=%s&p=%d%s" % (cat_name, page, rq_param)
                html = self._fetch(path)
                cards = self._parse_card_list(html)
            else:
                encoded_fenlei = urllib.parse.quote(tid)
                path = "/?fenlei=%s&p=%d%s" % (encoded_fenlei, page, rq_param)
                html = self._fetch(path)
                cards = self._parse_card_list(html)

            return {
                "page": page,
                "pagecount": page + 1 if len(cards) >= 12 else page,
                "limit": len(cards),
                "total": 9999,
                "list": cards
            }

        except Exception:
            return {"page": 1, "pagecount": 1, "limit": 20, "total": 0, "list": []}

    def detailContent(self, ids):
        raw_id = (ids or [""])[0]
        cid, _, pic = str(raw_id).partition("|")

        cid = re.sub(r'\D', '', cid) or cid
        path = "/?play-%s-1-.html" % cid
        html = self._fetch(path)

        title_match = re.search(r'<h1[^>]*>([\s\S]*?)</h1>', html)
        if not title_match:
            title_match = re.search(r'<title>([^<_\-]+)', html)
        vod_name = unescape(re.sub(r'<[^>]+>', '', title_match.group(1))).strip() if title_match else "正片"

        if not pic:
            pic_match = re.search(r'<img[^>]+?src=[\'"](https?://[^\'"]+)[\'"]', html)
            pic = pic_match.group(1).strip() if pic_match else ""

        vod = {
            "vod_id": raw_id,
            "vod_name": vod_name,
            "vod_pic": pic,
            "vod_actor": "📺TG群: https://t.me/+3t5XRPPo9mlkZDRl",
            "vod_director": "📺ZakaTV",
            "vod_content": "📺官方交流群: https://t.me/+3t5XRPPo9mlkZDRl | 严禁盗卖，完全免费！\n\n影片ID: %s" % cid,
            "vod_play_from": "Zaka专线",
            "vod_play_url": "正片$%s" % cid
        }

        return {"list": [vod]}

    def playerContent(self, flag, id, vipFlags):
        cid = str(id).split("|")[0].strip()
        api_path = "/?api=play&id=%s" % cid
        api_res = self._fetch(api_path, referer="%s/?play-%s-1-.html" % (self.site_url, cid))

        play_url = ""
        m = re.search(r'["\']url["\']\s*:\s*["\']([^"\']+)["\']', api_res)
        if m:
            play_url = m.group(1).replace("\\/", "/")
        else:
            m_direct = re.search(r'[\'"](https?://[^\'"]+?\.m3u8[^\'"]*)[\'"]', api_res)
            if m_direct:
                play_url = m_direct.group(1).replace("\\/", "/")

        return {
            "parse": 0,
            "url": play_url,
            "header": {
                "User-Agent": self.default_headers["User-Agent"],
                "Referer": self.site_url + "/"
            }
        }

    def searchContent(self, key, quick, pg="1"):
        try:
            encoded_key = urllib.parse.quote(key)
            page = int(pg) if pg else 1
            path = "/?search=%s&p=%d" % (encoded_key, page)
            html = self._fetch(path)
            cards = self._parse_card_list(html)
            return {"page": page, "pagecount": page + 1 if len(cards) >= 12 else page, "limit": len(cards), "total": 9999, "list": cards}
        except Exception:
            return {"page": 1, "pagecount": 1, "limit": 20, "total": 0, "list": []}

    def action(self, action):
        return None

    def liveContent(self):
        return ""

    def localProxy(self, params):
        return None

    def manualVideoCheck(self):
        return False

    def isVideoFormat(self, url):
        return False

    def destroy(self):
        pass
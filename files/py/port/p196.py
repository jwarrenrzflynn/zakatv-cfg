# coding=utf-8
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TVBox / 蜂蜜影视 (FongMi TV) 原生 Python 源脚本
站点: 奇优影院 (全量主分类 + 真实热播/更新大网格 + 理论片/热播播放完美修复终极交付版)
"""

import sys
import os
import re
import json
import ssl
import gzip
import zlib
import urllib.request
import urllib.parse
from urllib.parse import quote, unquote, urljoin

try:
    from base.spider import Spider as SpiderBase
except ImportError:
    class SpiderBase(object):
        def getCache(self, key): return None
        def setCache(self, key, value): return "fail"
        def delCache(self, key): return "fail"

def format_remarks(brand="ZakaTV", meta=""):
    clean_meta = str(meta or "").strip()
    clean_meta = re.sub(r"[\r\n\t]+", " ", clean_meta).strip()
    if clean_meta:
        return "%s | %s" % (brand, clean_meta)
    return brand

class Spider(SpiderBase):

    def __init__(self):
        super(Spider, self).__init__()
        self.siteUrl = "https://www.qyvod.com"
        self.tgGroup = "https://t.me/+3t5XRPPo9mlkZDRl"
        self.brandActor = "📺TG群: https://t.me/+3t5XRPPo9mlkZDRl"
        self.brandDirector = "📺ZakaTV"
        self._ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

        self.ctx = ssl.create_default_context()
        self.ctx.check_hostname = False
        self.ctx.verify_mode = ssl.CERT_NONE

        self.opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=self.ctx)
        )

    def init(self, extend=""):
        pass

    def getName(self):
        return "奇优影院·Zaka版"

    def isVideoFormat(self, url):
        low = (url or "").lower()
        return any(k in low for k in (".m3u8", ".mp4", ".flv", ".mkv", ".avi", ".ts", ".mpd", "index.png"))

    def manualVideoCheck(self):
        return False

    def _fetch(self, url, referer="", data=None):
        if not url:
            return {"code": 0, "text": "", "bytes": b""}
        if url.startswith("//"):
            url = "https:" + url
        elif url.startswith("/"):
            url = self.siteUrl + url

        headers = {
            "User-Agent": self._ua,
            "Referer": referer if referer else (self.siteUrl + "/"),
            "Accept": "*/*",
            "Accept-Encoding": "gzip, deflate"
        }

        req_body = None
        if data is not None:
            if isinstance(data, dict):
                req_body = urllib.parse.urlencode(data).encode("utf-8")
                headers["Content-Type"] = "application/x-www-form-urlencoded"
            elif isinstance(data, str):
                req_body = data.encode("utf-8")
                headers["Content-Type"] = "application/x-www-form-urlencoded"

        try:
            req = urllib.request.Request(url, data=req_body, headers=headers)
            with self.opener.open(req, timeout=12) as resp:
                code = resp.getcode()
                raw = resp.read()
                enc = resp.headers.get("Content-Encoding", "").lower()
                if raw.startswith(b"\x1f\x8b") or enc == "gzip":
                    try:
                        raw = gzip.decompress(raw)
                    except Exception:
                        pass
                elif enc == "deflate":
                    try:
                        raw = zlib.decompress(raw)
                    except Exception:
                        raw = zlib.decompress(raw, -zlib.MAX_WBITS)
                text = ""
                for c_enc in ("utf-8", "gbk", "gb2312"):
                    try:
                        text = raw.decode(c_enc)
                        break
                    except Exception:
                        continue
                if not text:
                    text = raw.decode("latin1", errors="ignore")
                return {"code": code, "text": text, "bytes": raw}
        except urllib.error.HTTPError as e:
            try:
                raw_err = e.read()
                return {"code": e.code, "text": raw_err.decode("utf-8", errors="ignore"), "bytes": raw_err}
            except Exception:
                return {"code": e.code, "text": "", "bytes": b""}
        except Exception:
            return {"code": -1, "text": "", "bytes": b""}

    def _fix_pic(self, path):
        if not path:
            return ""
        path = path.strip()
        if path.startswith("//"):
            return "https:" + path
        if path.startswith("/"):
            return self.siteUrl + path
        return path

    def _parse_vodlist(self, html):
        videos = []
        seen = set()

        blocks = re.findall(r'(<a[^>]+class=["\'][^"\']*(?:vodlist_thumb|ranklist_img|ranklist_thumb)[^"\']*["\'][\s\S]*?</a>)', html)
        if not blocks:
            blocks = re.findall(r'(<a[^>]+href=["\']/qyvod/\d+\.html["\'][\s\S]*?</a>)', html)

        for blk in blocks:
            href_m = re.search(r'href=["\'](/qyvod/\d+\.html)["\']', blk)
            if not href_m:
                continue
            href = href_m.group(1)
            if href in seen:
                continue
            seen.add(href)

            title_m = re.search(r'title=["\']([^"\']+)["\']', blk)
            title = title_m.group(1).strip() if title_m else ""

            pic_m = re.search(r'data-original=["\']([^"\']+)["\']', blk) or re.search(r'src=["\']([^"\']+)["\']', blk)
            pic = self._fix_pic(pic_m.group(1).strip() if pic_m else "")

            rem_m = re.search(r'<span[^>]+class=["\'][^"\']*pic_text[^"\']*["\'][^>]*>([^<]+)</span>', blk)
            remark = rem_m.group(1).strip() if rem_m else ""

            if not title:
                t_sub = re.findall(r'title=["\']([^"\']+)["\']', html[html.find(href):html.find(href)+200])
                title = t_sub[0] if t_sub else ""

            if title:
                videos.append({
                    "vod_id": href,
                    "vod_name": title,
                    "vod_pic": pic,
                    "vod_remarks": format_remarks("ZakaTV", remark),
                    "style": {"type": "rect", "ratio": 0.75}
                })

        return videos

    def homeContent(self, filter):
        cateManual = [
            {"type_name": "电影", "type_id": "1"},
            {"type_name": "连续剧", "type_id": "2"},
            {"type_name": "综艺", "type_id": "3"},
            {"type_name": "动漫", "type_id": "4"},
            {"type_name": "理论片", "type_id": "5"},
            {"type_name": "最新更新", "type_id": "map"},
            {"type_name": "热播排行", "type_id": "rank"}
        ]

        area_values = [
            {"n": "全部", "v": ""}, {"n": "大陆", "v": "大陆"}, {"n": "香港", "v": "香港"},
            {"n": "台湾", "v": "台湾"}, {"n": "美国", "v": "美国"}, {"n": "韩国", "v": "韩国"},
            {"n": "日本", "v": "日本"}, {"n": "泰国", "v": "泰国"}, {"n": "新加坡", "v": "新加坡"},
            {"n": "印度", "v": "印度"}, {"n": "英国", "v": "英国"}, {"n": "法国", "v": "法国"},
            {"n": "加拿大", "v": "加拿大"}, {"n": "西班牙", "v": "西班牙"}, {"n": "俄罗斯", "v": "俄罗斯"},
            {"n": "其它", "v": "其它"}
        ]

        year_values = [{"n": "全部", "v": ""}]
        for y in range(2026, 2012, -1):
            year_values.append({"n": str(y), "v": str(y)})

        by_values = [
            {"n": "按最新", "v": "time"},
            {"n": "按最热", "v": "hits"},
            {"n": "按评分", "v": "score"}
        ]

        class_filters = {
            "1": [
                {"n": "全部", "v": ""}, {"n": "动作片", "v": "动作"}, {"n": "喜剧片", "v": "喜剧"},
                {"n": "爱情片", "v": "爱情"}, {"n": "科幻片", "v": "科幻"}, {"n": "恐怖片", "v": "恐怖"},
                {"n": "剧情片", "v": "剧情"}, {"n": "战争片", "v": "战争"}, {"n": "纪录片", "v": "纪录"},
                {"n": "动画片", "v": "动画"}
            ],
            "2": [
                {"n": "全部", "v": ""}, {"n": "国产剧", "v": "国产"}, {"n": "香港剧", "v": "香港"},
                {"n": "台湾剧", "v": "台湾"}, {"n": "日本剧", "v": "日本"}, {"n": "韩国剧", "v": "韩国"},
                {"n": "欧美剧", "v": "欧美"}, {"n": "海外剧", "v": "海外"}, {"n": "短剧", "v": "短剧"}
            ],
            "3": [
                {"n": "全部", "v": ""}, {"n": "大陆综艺", "v": "大陆"}, {"n": "港台综艺", "v": "港台"},
                {"n": "日韩综艺", "v": "日韩"}, {"n": "欧美综艺", "v": "欧美"}
            ],
            "4": [
                {"n": "全部", "v": ""}, {"n": "国产动漫", "v": "国产"}, {"n": "日韩动漫", "v": "日韩"},
                {"n": "欧美动漫", "v": "欧美"}, {"n": "港台动漫", "v": "港台"}, {"n": "海外动漫", "v": "海外"}
            ],
            "5": [
                {"n": "全部", "v": ""}
            ]
        }

        filters = {}
        for item in cateManual:
            tid = item["type_id"]
            if tid in ("map", "rank"):
                continue
            filters[tid] = []
            if tid in class_filters and len(class_filters[tid]) > 1:
                filters[tid].append({"key": "class", "name": "分类", "value": class_filters[tid]})
            filters[tid].append({"key": "area", "name": "地区", "value": area_values})
            filters[tid].append({"key": "year", "name": "年份", "value": year_values})
            filters[tid].append({"key": "by", "name": "排序", "value": by_values})

        return {"class": cateManual, "filters": filters}

    def homeVideoContent(self):
        try:
            res = self._fetch(self.siteUrl + "/")
            html = res.get("text", "")
            return {"list": self._parse_vodlist(html)[:24]}
        except Exception:
            return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg) if pg else 1
        videos = []
        total_page = 1

        extend = extend or {}
        cls_val = extend.get("class", "")
        area_val = extend.get("area", "")
        year_val = extend.get("year", "")
        by_val = extend.get("by", "")

        try:
            if tid == "map":
                if page <= 1:
                    url = "%s/qyshow/1--time---------.html" % self.siteUrl
                else:
                    url = "%s/qyshow/1--time--------%d---.html" % (self.siteUrl, page)

                res = self._fetch(url)
                html = res.get("text", "")
                videos = self._parse_vodlist(html)
                pages_found = re.findall(r'/qyshow/\d+--time--------(\d+)---.html', html)
                total_page = max([int(p) for p in pages_found if p.isdigit()]) if pages_found else (page + 1)

            elif tid == "rank":
                if page <= 1:
                    url = "%s/qyshow/1--hits---------.html" % self.siteUrl
                else:
                    url = "%s/qyshow/1--hits--------%d---.html" % (self.siteUrl, page)

                res = self._fetch(url)
                html = res.get("text", "")
                videos = self._parse_vodlist(html)
                pages_found = re.findall(r'/qyshow/\d+--hits--------(\d+)---.html', html)
                total_page = max([int(p) for p in pages_found if p.isdigit()]) if pages_found else (page + 1)

            else:
                has_sub = any([cls_val, area_val, year_val, by_val, page > 1])
                if has_sub:
                    c_quote = quote(cls_val) if cls_val else ""
                    a_quote = quote(area_val) if area_val else ""
                    url = "%s/qyshow/%s-%s-%s-%s-----%d---%s.html" % (
                        self.siteUrl, tid, a_quote, by_val, c_quote, page, year_val
                    )
                else:
                    url = "%s/qylist/%s.html" % (self.siteUrl, tid)

                res = self._fetch(url)
                html = res.get("text", "")
                videos = self._parse_vodlist(html)

                pages_found = re.findall(r'/qyshow/[^"]*-----(\d+)---[^"]*\.html', html)
                if not pages_found:
                    pages_found = re.findall(r'/qyshow/\d+--------(\d+)---.html', html)
                if pages_found:
                    total_page = max([int(p) for p in pages_found if p.isdigit()])
                else:
                    total_page = page + 1 if len(videos) > 0 else 1

        except Exception:
            pass

        return {
            "page": page,
            "pagecount": total_page if total_page > 0 else 1,
            "limit": len(videos),
            "total": 9999 if len(videos) > 0 else 0,
            "list": videos
        }

    def detailContent(self, array):
        tid = array[0] if isinstance(array, (list, tuple)) else str(array)
        if not tid:
            return {"list": []}
        try:
            url = self.siteUrl + tid if not tid.startswith("http") else tid
            res = self._fetch(url)
            html = res.get("text", "")
            if not html:
                return {"list": []}

            title_m = re.search(r'<h1[^>]*>([^<]+)</h1>', html) or re.search(r'<title>《?(.*?)》?-', html)
            title = title_m.group(1).strip() if title_m else ""

            pic_m = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', html)
            if not pic_m:
                pic_m = re.search(r'data-original=["\']([^"\']+)["\']', html) or re.search(r'src=["\']([^"\']+)["\']', html)
            pic = self._fix_pic(pic_m.group(1).strip() if pic_m else "")

            area_m = re.search(r'<meta[^>]+property=["\']og:video:area["\'][^>]+content=["\']([^"\']+)["\']', html)
            area = area_m.group(1).strip() if area_m else ""

            year_m = re.search(r'年份[：:]\s*</span>\s*(\d{4})', html) or re.search(r'(\d{4})', html)
            year = year_m.group(1).strip() if year_m else ""

            desc_m = re.search(r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']', html)
            desc = desc_m.group(1).strip() if desc_m else ""

            playFrom = []
            playUrl = []

            playlist_blocks = re.findall(r'<ul[^>]+class=["\'][^"\']*(?:playlist|content_playlist)[^"\']*["\'][^>]*>([\s\S]*?)</ul>', html)
            if not playlist_blocks:
                playlist_blocks = re.findall(r'<ul[^>]+class=["\'][^"\']*clearfix[^"\']*["\'][^>]*>([\s\S]*?)</ul>', html)

            for idx, ul_body in enumerate(playlist_blocks):
                ep_matches = re.findall(r'<a[^>]+href=["\']([^"\']*(?:qyplay|\.html)[^"\']*)["\'][^>]*>([\s\S]*?)</a>', ul_body)
                episodes = []
                for ep_href, ep_raw in ep_matches:
                    clean_ep = re.sub(r'<[^>]+>', '', ep_raw).strip()
                    if not clean_ep:
                        ep_num_m = re.search(r'-(\d+)-(\d+)\.html', ep_href)
                        clean_ep = ("第%s集" % ep_num_m.group(2)) if ep_num_m else "正片"

                    if not any(bad in ep_href for bad in ("javascript", "#")) and "qyplay" in ep_href:
                        episodes.append("%s$%s" % (clean_ep, ep_href))

                if episodes:
                    playFrom.append("播放线路 %d" % (idx + 1))
                    playUrl.append("#".join(episodes))

            if not playFrom:
                all_qyplay = re.findall(r'href=["\'](/qyplay/[^"\']+)["\']', html)
                if all_qyplay:
                    episodes = []
                    seen_qp = set()
                    idx_cnt = 1
                    for qp in all_qyplay:
                        if qp not in seen_qp:
                            seen_qp.add(qp)
                            episodes.append("第%d集$%s" % (idx_cnt, qp))
                            idx_cnt += 1
                    if episodes:
                        playFrom.append("默认线路")
                        playUrl.append("#".join(episodes))

            full_desc = (
                "【🔥 官方交流群: %s】\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "%s"
            ) % (self.tgGroup, desc)

            vod = {
                "vod_id": tid,
                "vod_name": title,
                "vod_pic": pic,
                "vod_year": year,
                "vod_area": area,
                "vod_remarks": "ZakaTV",
                "vod_actor": self.brandActor,
                "vod_director": self.brandDirector,
                "vod_content": full_desc,
                "vod_play_from": "$$$".join(playFrom) if playFrom else "奇优播放",
                "vod_play_url": "$$$".join(playUrl) if playUrl else ("正片$" + tid)
            }
            return {"list": [vod]}
        except Exception:
            return {"list": []}

    def searchContent(self, key, quick, page="1"):
        try:
            url = "%s/search.php" % self.siteUrl
            post_data = {
                "searchword": key
            }
            res = self._fetch(url, referer=self.siteUrl + "/", data=post_data)
            html = res.get("text", "")
            return {"list": self._parse_vodlist(html)}
        except Exception:
            return {"list": []}

    def playerContent(self, flag, id, vipFlags):
        play_path = str(id).strip()
        full_url = self.siteUrl + play_path if not play_path.startswith("http") else play_path

        res = self._fetch(full_url)
        html = res.get("text", "")

        # 1. 深度解析 player_aaaa 提取直链
        p_json = re.search(r'var\s+player_aaaa\s*=\s*(\{[\s\S]*?\});', html) or re.search(r'player_data\s*=\s*(\{[\s\S]*?\});', html)
        if p_json:
            try:
                p_obj = json.loads(p_json.group(1))
                real_m3u8 = p_obj.get("url", "")
                if real_m3u8 and ".m3u8" in real_m3u8:
                    clean_m3u8 = real_m3u8.replace("\\/", "/")
                    # 关键修正：切片 CDN 直连，使用客户端原生 User-Agent 播放，杜绝被主站 Referer 丢包拦截
                    return {
                        "parse": 0,
                        "url": clean_m3u8,
                        "header": {
                            "User-Agent": self._ua
                        }
                    }
            except Exception:
                pass

        # 2. 从页面 script 或 iframe 提取直链
        m3u8_m = re.search(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*', html)
        if m3u8_m:
            return {
                "parse": 0,
                "url": m3u8_m.group(0),
                "header": {"User-Agent": self._ua}
            }

        iframes = re.findall(r'<iframe[^>]+src=["\']([^"\']+)["\']', html)
        for ifr in iframes:
            ifr_url = ifr if ifr.startswith("http") else urljoin(full_url, ifr)
            ifr_res = self._fetch(ifr_url, referer=full_url)
            ifr_html = ifr_res.get("text", "")
            m3u8_m = re.search(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*', ifr_html)
            if m3u8_m:
                return {
                    "parse": 0,
                    "url": m3u8_m.group(0),
                    "header": {"User-Agent": self._ua}
                }

        # 3. 兜底解析
        return {
            "parse": 1,
            "url": full_url,
            "header": {"User-Agent": self._ua}
        }

    def localProxy(self, params):
        return [404, "text/plain; charset=utf-8", "Proxy not configured"]
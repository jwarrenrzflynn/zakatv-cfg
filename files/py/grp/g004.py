#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 蜂蜜影视（FongMi TV）原生 Python 蜘蛛 - BestJavPorn
# 修复版：播放链路重做（2026-09-23）
#   - 列表 / 分类 / 搜索 / 详情 结构保持不变（只动了取流的层）
#   - 播放链路已按真站实测重写：原版走的 /api/play/ + video.bestjavporn.com/p/ 在真站上不存在
#     （/p/ 路径 404、/api/play/ 返回 {"status":false,"msg":"invalid sources"}）
#   - 真站实际链路：详情页 → #video-player[data-mpu] → 播放器页 video.bestjavporn.com/black.html?u=<host><path>
#     播放器页里再出正片流；本模块按「解析出直链就直接给 / 解析不出就把播放器页交给壳解析」两级兜底
#
# 可选：过盾中继（ext 里配 relay 或 pyrelay）
#   {"relay":"https://你的中继:端口"}   列表页/详情页被 CF 挡时自动走它，配了更稳，不配也能跑。

import sys
import os
import re
import json
import time
import base64
import html as html_lib
import urllib.request
import urllib.parse
from urllib.parse import urlparse, quote, unquote
import http.cookiejar
import gzip
import zlib
import ssl

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


# ───────────────────────── 播放链路常量（真站实测） ─────────────────────────

PLAYER_HOST = "https://video.bestjavporn.com"
PLAYER_PATH = "/black.html"
VIDEO_HOSTS = ("video.bestjavporn.com", "bestjavporn.com", "pornfhd.com", "doppiocdn", "mmcdn")

RE_M3U8 = re.compile(r'https?:\\?/\\?/[^\s"\'<>\\)]+?\.m3u8[^\s"\'<>\\)]*', re.I)
RE_MP4 = re.compile(r'https?:\\?/\\?/[^\s"\'<>\\)]+?\.mp4[^\s"\'<>\\)]*', re.I)
RE_IFRAME = re.compile(r'<iframe[^>]+src=["\']([^"\']+)["\']', re.I)
RE_SOURCE = re.compile(r'<(?:source|video)[^>]+src=["\']([^"\']+)["\']', re.I)
RE_HLS_LOAD = re.compile(r'loadSource\s*\(\s*["\']([^"\']+)["\']', re.I)
RE_FILE_JSON = re.compile(r'["\']file["\']\s*:\s*["\']([^"\']+)["\']', re.I)


class Spider(SpiderBase):
    def __init__(self):
        super(Spider, self).__init__()
        self.siteUrl = "https://www.bestjavporn.com"
        self.tgGroup = "https://t.me/+3t5XRPPo9mlkZDRl"
        self.brandActor = "📺TG群: https://t.me/+3t5XRPPo9mlkZDRl"
        self.brandDirector = "📺ZakaTV"
        self._ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        self.options = {}
        self.relay = ""
        self._cache = {}

        self.ctx = ssl.create_default_context()
        self.ctx.check_hostname = False
        self.ctx.verify_mode = ssl.CERT_NONE

        self.cj = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cj),
            urllib.request.HTTPSHandler(context=self.ctx)
        )

    def init(self, extend=""):
        if isinstance(extend, dict):
            self.options = extend
        elif extend:
            try:
                self.options = json.loads(extend)
            except Exception:
                self.options = {}
        self.relay = str(self.options.get("relay") or self.options.get("pyrelay") or "").strip().rstrip("/")
        if self.relay.lower() in ("off", "none", "-", "0", "关闭"):
            self.relay = ""
        return True

    def getName(self):
        return "Zaka·BestJavPorn"

    def isVideoFormat(self, url):
        low = (url or "").lower()
        if any(bad in low for bad in ("preview.mp4", "sample.mp4", "trailer.mp4", "top_banner")):
            return False
        return any(k in low for k in (".m3u8", ".mp4", ".flv", ".mkv", ".avi", ".ts", ".mpd"))

    def manualVideoCheck(self):
        return False

    # ───────────────────────── HTTP 层 ─────────────────────────

    def _raw(self, target_url, data=None, referer="", headers_custom=None, timeout=15):
        """直连请求（带 cookie jar）。返回 dict，永不抛异常。"""
        if not target_url:
            return {"code": 0, "text": "", "bytes": b"", "err": "empty url", "final_url": ""}
        if target_url.startswith("//"):
            target_url = "https:" + target_url
        elif target_url.startswith("/"):
            target_url = self.siteUrl + target_url

        headers = {
            "User-Agent": self._ua,
            "Referer": referer if referer else (self.siteUrl + "/"),
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive"
        }
        if headers_custom:
            headers.update(headers_custom)

        req_data = None
        if data is not None:
            if isinstance(data, dict):
                req_data = urllib.parse.urlencode(data).encode("utf-8")
                headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
                headers["X-Requested-With"] = "XMLHttpRequest"
            elif isinstance(data, (bytes, str)):
                req_data = data.encode("utf-8") if isinstance(data, str) else data

        try:
            req = urllib.request.Request(target_url, data=req_data, headers=headers)
            with self.opener.open(req, timeout=timeout) as resp:
                code = resp.getcode()
                final_url = resp.geturl()
                raw = resp.read()
                enc = ""
                try:
                    enc = resp.headers.get("Content-Encoding", "") or ""
                except Exception:
                    enc = ""
                if raw.startswith(b"\x1f\x8b") or "gzip" in enc:
                    try:
                        raw = gzip.decompress(raw)
                    except Exception:
                        pass
                elif "deflate" in enc:
                    try:
                        raw = zlib.decompress(raw)
                    except Exception:
                        try:
                            raw = zlib.decompress(raw, -zlib.MAX_WBITS)
                        except Exception:
                            pass
                try:
                    text = raw.decode("utf-8")
                except Exception:
                    text = raw.decode("latin1", errors="ignore")
                return {"code": code, "text": text, "bytes": raw, "err": "", "final_url": final_url}
        except Exception as e:
            return {"code": -1, "text": "", "bytes": b"", "err": str(e), "final_url": target_url}

    def _relay(self, ep, url, referer="", timeout=30):
        """经中继取页：<relay>/fs?u=&r= 。没配中继或失败都返回空串。"""
        if not self.relay or not url:
            return ""
        api = "%s%s?u=%s" % (self.relay, ep, quote(url, safe=""))
        if referer:
            api += "&r=" + quote(referer, safe="")
        res = self._raw(api, referer=referer, timeout=timeout)
        if res.get("code") != 200:
            return ""
        html = res.get("text", "")
        low = html.lower()
        if len(html) < 500 or "just a moment" in low or "challenge-platform" in low:
            return ""
        return html

    def _fetch(self, target_url, referer="", timeout=15, relay_first=False, is_document=True):
        """
        取页面：配了中继就先走中继（过 CF 盾），拿不到再直连；
        没配中继就直连。返回原来的 res dict（保持调用方不变）。
        """
        if relay_first and self.relay and is_document:
            html = self._relay("/fs", target_url, referer or (self.siteUrl + "/"), timeout=max(timeout, 25))
            if html:
                return {"code": 200, "text": html, "bytes": html.encode("utf-8"), "err": "", "final_url": target_url}
        res = self._raw(target_url, referer=referer, timeout=timeout)
        txt = (res.get("text") or "").lower()
        if (res.get("code") != 200 or "just a moment" in txt or "challenge-platform" in txt) and self.relay and is_document:
            html = self._relay("/fs", target_url, referer or (self.siteUrl + "/"), timeout=max(timeout, 25))
            if html:
                return {"code": 200, "text": html, "bytes": html.encode("utf-8"), "err": "", "final_url": target_url}
        return res

    def _clean_text(self, raw):
        t = re.sub(r'<[^>]+>', '', raw or '')
        t = html_lib.unescape(t)
        return re.sub(r'[\r\n\t\s]+', ' ', t).strip()

    # ───────────────────────── 首页 / 分类 / 详情 ─────────────────────────

    def homeContent(self, filter):
        result = {
            "class": [
                {"type_name": "有码专区", "type_id": "censored"},
                {"type_name": "无码专区", "type_id": "uncensored"},
                {"type_name": "中英字幕", "type_id": "subbed"},
                {"type_name": "素人专区", "type_id": "amateur"},
                {"type_name": "去码无码", "type_id": "decensored"},
                {"type_name": "分类大全", "type_id": "folder_categories"},
                {"type_name": "女优演员", "type_id": "folder_pornstars"},
                {"type_name": "制片厂商", "type_id": "folder_studios"}
            ]
        }
        if filter:
            result["filters"] = {
                "subbed": [
                    {
                        "key": "sub_lang",
                        "name": "字幕语言",
                        "init": "chinese",
                        "value": [
                            {"n": "中文字幕", "v": "chinese"},
                            {"n": "英文字幕", "v": "english"},
                            {"n": "印尼字幕", "v": "indo"}
                        ]
                    }
                ]
            }
        return result

    def homeVideoContent(self):
        return self.categoryContent("censored", 1, None, {})

    def _extract_real_img(self, chunk):
        for attr in ("data-lazy-src", "data-wpsrc", "data-original", "data-src"):
            m = re.search(r'\b%s=["\']([^"\']+)["\']' % attr, chunk, re.I)
            if m:
                val = m.group(1).strip()
                if val and not val.startswith("data:image/svg") and not val.endswith("/404.png"):
                    return val

        noscript_m = re.search(r'<noscript[^>]*>([\s\S]*?)</noscript>', chunk, re.I)
        if noscript_m:
            src_m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', noscript_m.group(1), re.I)
            if src_m:
                val = src_m.group(1).strip()
                if val and not val.startswith("data:image/svg") and not val.endswith("/404.png"):
                    return val

        src_m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', chunk, re.I)
        if src_m:
            val = src_m.group(1).strip()
            if val and not val.startswith("data:image/svg") and not val.endswith("/404.png"):
                return val

        bg_m = re.search(r'background(?:-image)?\s*:\s*url\(["\']?([^"\')]+)["\']?\)', chunk, re.I)
        if bg_m:
            val = bg_m.group(1).strip()
            if val and not val.startswith("data:image/svg"):
                return val

        return ""

    def _wrap_img(self, img_url):
        if not img_url:
            return ""
        if not img_url.startswith("http"):
            img_url = urllib.parse.urljoin(self.siteUrl, img_url)
        return "%s@Referer=%s@User-Agent=%s" % (img_url, self.siteUrl + "/", quote(self._ua))

    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg) if pg else 1
        raw_target = str(tid).strip()

        is_sub_flow = False
        if raw_target.startswith("folder@@"):
            is_sub_flow = True
            base_url = raw_target.replace("folder@@", "")
            if page > 1:
                req_url = base_url.rstrip("/") + ("/page/%d/" % page)
            else:
                req_url = base_url
        else:
            route_map = {
                "censored": "/v36/category/censored/",
                "uncensored": "/v11/category/uncensored/",
                "amateur": "/v20/category/amateur/",
                "decensored": "/v22/category/decensored/",
                "folder_categories": "/categories/",
                "folder_pornstars": "/pornstars/",
                "folder_studios": "/studios/"
            }

            if raw_target == "subbed":
                lang = (extend or {}).get("sub_lang", "chinese")
                if lang == "chinese":
                    base_path = "/v14/category/chinese-subtitle/"
                elif lang == "indo":
                    base_path = "/v2/category/subtitle-indonesia/"
                else:
                    base_path = "/v8/category/censored/english-subtitle/"
            elif raw_target in route_map:
                base_path = route_map[raw_target]
            else:
                base_path = raw_target if raw_target.startswith("/") else ("/" + raw_target)
                if not base_path.endswith("/"):
                    base_path += "/"

            if page > 1:
                req_url = self.siteUrl + ("%spage/%d/" % (base_path.rstrip("/") + "/", page))
            else:
                req_url = self.siteUrl + base_path

        res = self._fetch(req_url, relay_first=True)
        html = res.get("text", "")
        if not html:
            return {"page": page, "pagecount": 1, "limit": 0, "total": 0, "list": []}

        scoped_html = re.sub(r'<header[^>]*>[\s\S]*?</header>', '', html, flags=re.I)
        scoped_html = re.sub(r'<nav[^>]*>[\s\S]*?</nav>', '', scoped_html, flags=re.I)
        scoped_html = re.sub(r'<footer[^>]*>[\s\S]*?</footer>', '', scoped_html, flags=re.I)

        is_first_level_folder = (not is_sub_flow) and (raw_target in ("folder_categories", "folder_pornstars", "folder_studios") or any(k in req_url for k in ("/categories/", "/pornstars/", "/studios/")))

        chunks = []
        for split_key in ('class="thumb', 'class="post-', 'class="video-block', 'class="item'):
            parts = scoped_html.split(split_key)
            if len(parts) > 2:
                chunks = parts[1:]
                break

        if not chunks:
            chunks = re.findall(r'(<(?:div|article|li)[^>]*(?:item|video|thumb|post)[^>]*>[\s\S]*?</(?:div|article|li)>)', scoped_html, re.I)

        video_list = []
        for chunk in chunks:
            link_m = re.search(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*title=["\']([^"\']+)["\']', chunk, re.I)
            if not link_m:
                link_m = re.search(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>([\s\S]*?)</a>', chunk, re.I)
            if not link_m:
                continue

            href = link_m.group(1).strip()
            title = self._clean_text(link_m.group(2))
            if not href or href.startswith("javascript:") or href in ("#", "/"):
                continue

            full_href = href if href.startswith("http") else urllib.parse.urljoin(self.siteUrl, href)
            raw_pic = self._extract_real_img(chunk)
            wrapped_pic = self._wrap_img(raw_pic)

            dur_m = re.search(r'class="duration"[^>]*>[\s\S]*?</i>\s*([0-9:]+)', chunk, re.I)
            if not dur_m:
                dur_m = re.search(r'(?:duration|time|badge)[^>]*>([\s\S]*?)</', chunk, re.I)
            duration = self._clean_text(dur_m.group(1)) if dur_m else ""

            if is_first_level_folder:
                is_actor = "pornstar" in req_url
                card = {
                    "vod_id": "folder@@" + full_href,
                    "vod_name": title or "未知目录",
                    "vod_pic": wrapped_pic,
                    "vod_remarks": format_remarks("ZakaTV", "作品集"),
                    "vod_tag": "folder",
                    "style": {"type": "oval" if is_actor else "rect", "ratio": 1.0 if is_actor else 1.78}
                }
            else:
                card = {
                    "vod_id": full_href,
                    "vod_name": title or "未知片目",
                    "vod_pic": wrapped_pic,
                    "vod_remarks": format_remarks("ZakaTV", duration),
                    "style": {"type": "rect", "ratio": 1.78}
                }
            video_list.append(card)

        has_next = ('page/%d/' % (page + 1)) in scoped_html
        pagecount = (page + 1) if has_next else page

        return {
            "page": page,
            "pagecount": max(pagecount, 1),
            "limit": len(video_list),
            "total": 9999 if has_next else len(video_list),
            "list": video_list
        }

    def detailContent(self, ids):
        raw_id = ids[0] if isinstance(ids, (list, tuple)) else str(ids)
        target_url = str(raw_id)

        if target_url.startswith("folder@@"):
            return self.categoryContent(target_url, 1, None, {})

        res = self._fetch(target_url, relay_first=True)
        html = res.get("text", "")

        title_m = re.search(r'<h1[^>]*>([\s\S]*?)</h1>', html, re.I)
        title = self._clean_text(title_m.group(1)) if title_m else "正片详情"

        raw_cover = self._extract_real_img(html)
        cover = self._wrap_img(raw_cover)

        dur_m = re.search(r'itemprop="duration"\s+content="P0DT([^"]+)"', html)
        dur_str = dur_m.group(1).lower() if dur_m else ""

        # 播放器页地址：真站由主题脚本按「当前页 host+path」拼出来（实测）
        play_url = self._player_url(target_url)

        intro = (
            "【🔥 ZakaTV交流群: %s】\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "• 影片标题: %s\n"
            "• 官方正片时长: %s\n"
            "• 播放通道: BestJavPorn 官方播放器 (完整正片)"
        ) % (self.tgGroup, title, dur_str if dur_str else "完整正片")

        return {
            "list": [{
                "vod_id": target_url,
                "vod_name": title,
                "vod_pic": cover,
                "vod_actor": self.brandActor,
                "vod_director": self.brandDirector,
                "vod_remarks": "ZakaTV",
                "vod_content": intro.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"),
                "vod_play_from": "Zaka专线",
                "vod_play_url": "超清正片$%s" % play_url
            }]
        }

    # ───────────────────────── 播放链路（本轮重写） ─────────────────────────

    def _player_url(self, page_url):
        """
        详情页 → 播放器页。
        真站实测：主题脚本 cast.js 往页面里注入
            https://video.bestjavporn.com/black.html?u=<当前页 host+path>
        （u 参数不带协议头，也不带 mpu；mpu 是留个页面自己用的）
        """
        u = re.sub(r'^https?://', '', str(page_url or "").strip())
        u = u.split("#")[0]
        if not u:
            return ""
        return "%s%s?u=%s" % (PLAYER_HOST, PLAYER_PATH, u)

    @staticmethod
    def _abs(base, ref):
        if not ref:
            return ""
        t = ref.strip().replace("\\/", "/").replace("&amp;", "&")
        if t.startswith("//"):
            return "https:" + t
        if t.startswith("http"):
            return t
        try:
            return urllib.parse.urljoin(base, t)
        except Exception:
            return t

    def _pick(self, html, pattern, base, bad_words=("preview", "sample", "trailer", "banner", "ad_")):
        for m in re.finditer(pattern, html or ""):
            url = self._abs(base, m.group(1) if m.groups() else m.group(0))
            low = url.lower()
            if not url or any(b in low for b in bad_words):
                continue
            return url
        return ""

    def _extract_from_player_html(self, html, player_url):
        """从播放器页 HTML 里抠流地址：明文 m3u8 → 各播放器变量 → mp4 → 内嵌 iframe。"""
        if not html:
            return "", ""

        m3u8 = self._pick(html, RE_M3U8, player_url)
        if not m3u8:
            m3u8 = self._pick(html, RE_HLS_LOAD, player_url)
        if m3u8:
            return m3u8, ""

        direct = self._pick(html, RE_SOURCE, player_url)
        if not direct:
            direct = self._pick(html, RE_FILE_JSON, player_url)
        if not direct:
            direct = self._pick(html, RE_MP4, player_url)
        if direct:
            return "", direct

        return "", ""

    def _resolve(self, player_url, referer, depth=0):
        """
        逐层解析：播放器页 → (m3u8 | mp4 | 内嵌 iframe 再进一层)
        返回 (stream_url, kind, final_page)
        """
        if depth > 2 or not player_url:
            return "", "", ""

        res = self._fetch(player_url, referer=referer, timeout=18, relay_first=False)
        html = (res.get("text", "") or "").replace("\\/", "/").replace("&amp;", "&")
        final_page = res.get("final_url") or player_url

        m3u8, direct = self._extract_from_player_html(html, final_page)
        if m3u8:
            return m3u8, "m3u8", final_page
        if direct:
            return direct, "mp4", final_page

        # 内嵌播放器：进一层（只认视频域/播放器域，别被广告 iframe 带跑）
        for m in re.finditer(RE_IFRAME, html, re.I):
            sub = self._abs(final_page, m.group(1))
            low = sub.lower()
            if any(h in low for h in VIDEO_HOSTS) and not any(b in low for b in ("magsrv", "whitetrafsa", "chaturbate", "stripchat", "tapioni")):
                s, k, p = self._resolve(sub, final_page, depth + 1)
                if s:
                    return s, k, p

        return "", "", final_page

    def playerContent(self, flag, id, vipFlags):
        raw_target = str(id).strip()
        player_url = ""
        referer = self.siteUrl + "/"

        if raw_target.startswith("http"):
            player_url = raw_target
            m = re.search(r'[?&]u=([^&]+)', raw_target)
            if m:
                path = unquote(m.group(1))
                referer = "https://" + path if not path.startswith("http") else path
        elif raw_target.startswith("player@@"):
            parts = raw_target.split("@@")
            referer = parts[1]
            player_url = self._player_url(referer)

        headers = {
            "User-Agent": self._ua,
            "Referer": referer,
            "Origin": "https://www.bestjavporn.com"
        }

        if not player_url:
            return {"parse": 0, "playUrl": "", "url": "", "header": headers}

        # 一级：直接解析出流
        stream, kind, final_page = self._resolve(player_url, referer)
        if stream:
            sugar = ";".join(["%s=%s" % (k, quote(v)) for k, v in headers.items()])
            return {
                "parse": 0,
                "playUrl": "",
                "url": "%s;%s" % (stream, sugar),
                "header": headers
            }

        # 二级：解析不出就把播放器页交给壳（壳里是浏览器环境，能跑播放器自己的脚本）
        sugar = ";".join(["%s=%s" % (k, quote(v)) for k, v in headers.items()])
        return {
            "parse": 1,
            "playUrl": "",
            "url": "%s;%s" % (final_page or player_url, sugar),
            "header": headers
        }

    def searchContent(self, key, quick, pg="1"):
        page = int(pg) if pg else 1
        query_kw = quote(str(key).strip())
        search_path = "/page/%d/?s=%s" % (page, query_kw) if page > 1 else "/?s=%s" % query_kw
        return self.categoryContent(search_path, page, None, {})

    def localProxy(self, params):
        url = params.get("url", "")
        if not url:
            return [404, "text/plain; charset=utf-8", "Missing url parameter"]
        res = self._raw(url, referer=self.siteUrl + "/")
        raw_b = res.get("bytes", b"")
        mime = "image/jpeg"
        if raw_b.startswith(b"\x89PNG"):
            mime = "image/png"
        elif raw_b.startswith(b"GIF8"):
            mime = "image/gif"
        elif raw_b.startswith(b"RIFF"):
            mime = "image/webp"
        return [res.get("code", 200), mime, raw_b]

    def action(self, action):
        return {"msg": "ok"}

    def liveContent(self):
        return ""

    def destroy(self):
        self.options = {}

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import re
import json
import base64
import html as html_lib
import urllib.request
import urllib.parse
from urllib.parse import quote, unquote
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


class Spider(SpiderBase):
    def __init__(self):
        super(Spider, self).__init__()
        self.navUrls = ["https://x99dh.cc", "https://x99dh.one"]
        self.defaultHost = "https://madou8.pw"
        self.siteUrl = self.defaultHost
        self.siteName = "LissAV"
        self.targetOrigin = "https://madou8.pw"
        self.tgGroup = "https://t.me/+3t5XRPPo9mlkZDRl"
        self.brandActor = "📺TG群: https://t.me/+3t5XRPPo9mlkZDRl"
        self.brandDirector = "📺ZakaTV"
        self._ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        self.options = {}

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

        cached_site = self.getCache("lissav_jp_dynamic_site_url")
        if cached_site and str(cached_site).startswith("http"):
            self.siteUrl = str(cached_site).strip().rstrip("/")
        else:
            self._refresh_site_url()
        return True

    def getName(self):
        return "LissAV"

    def isVideoFormat(self, url):
        if not url:
            return False
        low = url.lower()
        if any(bad in low for bad in ("preview.mp4", "sample.mp4", "trailer.mp4", "player.centercdn.top")):
            return False
        return any(k in low for k in (".m3u8", ".mp4", ".flv", ".mkv", ".avi", ".ts", ".mpd", ".jpeg", "video.jpeg", "index.png"))

    def manualVideoCheck(self):
        return False

    def _refresh_site_url(self):
        headers = {
            "User-Agent": self._ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate"
        }

        for nav in self.navUrls:
            text = ""
            try:
                req = urllib.request.Request(nav, headers=headers)
                with self.opener.open(req, timeout=8) as resp:
                    raw = resp.read()
                    enc = getattr(resp, "headers", {}).get("Content-Encoding", "")
                    if raw.startswith(b"\x1f\x8b") or enc == "gzip":
                        raw = gzip.decompress(raw)
                    text = raw.decode("utf-8", errors="ignore")
            except Exception:
                continue

            if not text:
                continue

            b64_blocks = re.findall(r'["\']([A-Za-z0-9+/=]{100,})["\']', text)
            for b in b64_blocks:
                try:
                    decoded = base64.b64decode(b).decode("utf-8", errors="ignore")
                    unquoted = urllib.parse.unquote(decoded)
                    if "[" in unquoted and self.siteName in unquoted:
                        site_list = json.loads(unquoted)
                        for item in site_list:
                            name = item.get("name", "").strip()
                            if name == self.siteName:
                                cand_urls = []
                                main_url = item.get("url", "")
                                if main_url:
                                    cand_urls.append(main_url)
                                for u_obj in item.get("urls", []):
                                    u = u_obj.get("url", "")
                                    if u and u not in cand_urls:
                                        cand_urls.append(u)

                                for c_url in cand_urls:
                                    parsed = urllib.parse.urlparse(c_url)
                                    base = "%s://%s" % (parsed.scheme, parsed.netloc)
                                    chk = self._fetch(base + "/asian/zh-CN", check_host=False)
                                    if chk.get("code") == 200:
                                        self.siteUrl = base
                                        self.setCache("lissav_jp_dynamic_site_url", base)
                                        return True
                except Exception:
                    continue
        return False

    def _fetch(self, target_url, referer="", check_host=True):
        if not target_url:
            return {"code": 0, "text": "", "bytes": b"", "err": "", "final_url": ""}
        if target_url.startswith("//"):
            target_url = "https:" + target_url
        elif target_url.startswith("/"):
            target_url = self.siteUrl + target_url

        headers = {
            "User-Agent": self._ua,
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        }
        if referer:
            headers["Referer"] = referer

        last_err = ""
        domain_retried = False

        for attempt in range(2):
            try:
                req = urllib.request.Request(target_url, headers=headers)
                with self.opener.open(req, timeout=12) as resp:
                    code = resp.getcode()
                    final_url = resp.geturl()
                    raw = resp.read()
                    enc = getattr(resp, "headers", {}).get("Content-Encoding", "")
                    if raw.startswith(b"\x1f\x8b") or enc == "gzip":
                        raw = gzip.decompress(raw)
                    elif enc == "deflate":
                        try:
                            raw = zlib.decompress(raw)
                        except Exception:
                            raw = zlib.decompress(raw, -zlib.MAX_WBITS)
                    try:
                        text = raw.decode("utf-8")
                    except Exception:
                        text = raw.decode("latin1", errors="ignore")
                    return {"code": code, "text": text, "bytes": raw, "err": "", "final_url": final_url}
            except urllib.error.HTTPError as e:
                last_err = "HTTP %s" % e.code
                if e.code in (404, 451, 502, 503) and check_host and not domain_retried:
                    old_host = urllib.parse.urlparse(self.siteUrl).netloc
                    self.delCache("lissav_jp_dynamic_site_url")
                    if self._refresh_site_url():
                        domain_retried = True
                        new_host = urllib.parse.urlparse(self.siteUrl).netloc
                        target_url = target_url.replace(old_host, new_host)
                        continue
                if e.code in (451, 403, 429) and attempt == 0:
                    continue
                return {"code": e.code, "text": "", "bytes": b"", "err": str(e), "final_url": target_url}
            except Exception as e:
                last_err = str(e)
                if check_host and not domain_retried:
                    old_host = urllib.parse.urlparse(self.siteUrl).netloc
                    self.delCache("lissav_jp_dynamic_site_url")
                    if self._refresh_site_url():
                        domain_retried = True
                        new_host = urllib.parse.urlparse(self.siteUrl).netloc
                        target_url = target_url.replace(old_host, new_host)
                        continue
                if attempt == 0:
                    continue
                return {"code": -1, "text": "", "bytes": b"", "err": str(e), "final_url": target_url}

        return {"code": -1, "text": "", "bytes": b"", "err": last_err, "final_url": target_url}

    def homeContent(self, filter):
        result = {
            "class": [
                {"type_name": "🔥 今日热门", "type_id": "/asian/zh-CN/videos/hot/today"},
                {"type_name": "✨ 最近更新", "type_id": "/asian/zh-CN/videos/recent"},
                {"type_name": "🆕 新作上市", "type_id": "/asian/zh-CN/videos/new-releases"},
                {"type_name": "📱 无码流出", "type_id": "/asian/zh-CN/videos/tag/无码流出"},
                {"type_name": "🀄 中文字幕", "type_id": "/asian/zh-CN/videos/tag/中文字幕"},
                {"type_name": "巨乳", "type_id": "/asian/zh-CN/videos/tag/巨乳"},
                {"type_name": "人妻", "type_id": "/asian/zh-CN/videos/tag/人妻"},
                {"type_name": "熟女", "type_id": "/asian/zh-CN/videos/tag/熟女"},
                {"type_name": "丝袜", "type_id": "/asian/zh-CN/videos/tag/丝袜"}
            ]
        }
        if filter:
            result["filters"] = {}
        return result

    def homeVideoContent(self):
        return {"list": []}

    def _parse_vod_list(self, html_text):
        cards = []
        seen_cid = set()

        blocks = re.findall(r'<a[^>]+href=["\'](/[^"\']*/video/cid/([^"\'/?#]+))["\'][^>]*>([\s\S]*?)</a>', html_text, re.I)
        for href, cid, block in blocks:
            cid_clean = cid.strip().lower()
            if not cid_clean or cid_clean in seen_cid:
                continue

            block_low = block.lower()
            if any(bad in block_low for bad in ("9527.men", "9527", "迁移至", "迁往", "迁至", "新网址", "地址发布", "永久回家")):
                continue

            img_src = ""
            for pat in [
                r'src=["\']([^"\']+)["\']',
                r'data-src=["\']([^"\']+)["\']',
                r'data-original=["\']([^"\']+)["\']'
            ]:
                m = re.search(pat, block, re.I)
                if m:
                    cand = m.group(1).strip()
                    cand_low = cand.lower()
                    if cand_low.endswith(".svg") or "data:image" in cand_low:
                        continue
                    if any(bad in cand_low for bad in ("9527", "banner", "notice", "ad_")):
                        continue
                    img_src = cand
                    break

            if not img_src:
                continue

            title_m = re.search(r'(?:title|alt)=["\']([^"\']+)["\']', block, re.I)
            title = title_m.group(1).strip() if title_m else ""
            if not title:
                clean_text = re.sub(r'<[^>]+>', '', block).strip()
                title = clean_text.split("\n")[0].strip() if clean_text else ""

            if not title:
                continue

            title_low = title.lower()
            if any(bad in title_low for bad in ("9527", "迁移", "新网址", "导航", "地址发布")):
                continue

            seen_cid.add(cid_clean)

            dur_m = re.search(r'(\d{1,2}:\d{2}(?::\d{2})?)', block)
            dur = dur_m.group(1) if dur_m else "HD"

            if img_src.startswith("//"):
                img_src = "https:" + img_src
            elif img_src.startswith("/"):
                img_src = self.siteUrl + img_src

            payload = {"url": href.strip(), "title": html_lib.unescape(title)}
            b64_info = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")

            cards.append({
                "vod_id": "pkg_" + b64_info,
                "vod_name": html_lib.unescape(title),
                "vod_pic": img_src,
                "vod_remarks": format_remarks("ZakaTV", dur),
                "style": {"type": "rect", "ratio": 1.78}
            })

        return cards

    def categoryContent(self, tid, pg, filter, extend):
        del filter, extend
        page_num = int(pg) if str(pg).isdigit() else 1

        path = str(tid).strip()
        sep = "&" if "?" in path else "?"
        raw_url = "%s%spage=%d" % (path, sep, page_num)
        req_url = urllib.parse.quote(raw_url, safe="/?=&:%")

        res = self._fetch(req_url, referer=self.siteUrl + "/asian/zh-CN")
        cards = self._parse_vod_list(res.get("text", ""))

        return {
            "page": page_num,
            "pagecount": page_num + 1 if len(cards) >= 12 else page_num,
            "limit": len(cards),
            "total": 9999,
            "list": cards
        }

    def detailContent(self, ids):
        raw_id = ids[0] if isinstance(ids, (list, tuple)) else str(ids)
        target_path = ""
        cached_title = ""

        if str(raw_id).startswith("pkg_"):
            try:
                b64_str = raw_id[4:]
                pad = len(b64_str) % 4
                if pad:
                    b64_str += "=" * (4 - pad)
                pkg = json.loads(base64.urlsafe_b64decode(b64_str.encode("utf-8")).decode("utf-8"))
                target_path = pkg.get("url", "")
                cached_title = pkg.get("title", "")
            except Exception:
                target_path = raw_id
        else:
            target_path = str(raw_id).strip()

        res = self._fetch(target_path, referer=self.siteUrl + "/asian/zh-CN")
        html_text = res.get("text", "")

        vod_name = cached_title
        if not vod_name:
            m_schema = re.search(r'["\']name["\']\s*:\s*["\']([^"\']+)["\']', html_text)
            if m_schema:
                cand = m_schema.group(1).strip()
                if cand and cand != "VideoObject":
                    vod_name = html_lib.unescape(cand)

        if not vod_name:
            h1_m = re.search(r'<h1[^>]*>([\s\S]*?)</h1>', html_text, re.I)
            if h1_m:
                clean_h1 = re.sub(r'<[^>]+>', '', h1_m.group(1)).strip()
                if clean_h1:
                    vod_name = html_lib.unescape(clean_h1)

        if not vod_name:
            name_m = re.search(r'<title>([^<]+)</title>', html_text, re.I)
            if name_m:
                raw_title = html_lib.unescape(name_m.group(1).strip())
                for brand in ["- LissAV", "| LissAV", "LissAV"]:
                    raw_title = raw_title.replace(brand, "")
                vod_name = raw_title.strip(" -|_")

        if not vod_name:
            vod_name = "日本精选视频"

        vod_pic = ""
        pic_m = re.search(r'poster:\s*["\']([^"\']+)["\']', html_text)
        if not pic_m:
            pic_m = re.search(r'property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', html_text, re.I)
        if pic_m:
            cand_p = pic_m.group(1).strip()
            if not any(bad in cand_p.lower() for bad in ("9527", "banner", "notice")):
                vod_pic = cand_p

        video_uid = ""
        m_uid = re.search(r'var\s+videoUid\s*=\s*["\']([a-zA-Z0-9_-]+)["\']', html_text)
        if not m_uid:
            m_uid = re.search(r'["\']videoUid["\']\s*:\s*["\']([a-zA-Z0-9_-]+)["\']', html_text)
        if m_uid:
            video_uid = m_uid.group(1).strip()

        stream_api = "/asian/zh-CN/api/video/stream"
        m_api = re.search(r'var\s+streamApi\s*=\s*["\']([^"\']+)["\']', html_text)
        if m_api:
            stream_api = m_api.group(1).strip()

        play_token = "%s@@%s@@%s" % (
            video_uid if video_uid else "",
            stream_api,
            target_path
        )

        full_desc = (
            "【🔥 官方交流群: %s】\n"
            "【当前发布域名: %s】\n"
            "【番号/UID】: %s\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "极速动态调度专线"
        ) % (self.tgGroup, self.siteUrl, video_uid if video_uid else target_path)

        escaped_desc = full_desc.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        play_lines = [
            "超清自愈专线1$%s@@0" % play_token,
            "备用防阻断专线2$%s@@1" % play_token,
            "备用防阻断专线3$%s@@2" % play_token
        ]

        return {
            "list": [{
                "vod_id": raw_id,
                "vod_name": html_lib.unescape(vod_name),
                "vod_pic": vod_pic,
                "vod_actor": self.brandActor,
                "vod_director": self.brandDirector,
                "vod_remarks": format_remarks("ZakaTV", "正片"),
                "vod_content": escaped_desc,
                "vod_play_from": "LissAV极速专线",
                "vod_play_url": "#".join(play_lines)
            }]
        }

    def playerContent(self, flag, id, vipFlags):
        del flag, vipFlags
        raw_id = str(id).strip()

        target_stream_url = ""
        if "@@" in raw_id:
            parts = raw_id.split("@@")
            video_uid = parts[0]
            stream_api = parts[1] if len(parts) > 1 else "/asian/zh-CN/api/video/stream"
            target_path = parts[2] if len(parts) > 2 else ""
            line_idx = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0

            if video_uid:
                dispatch_url = "%s%s?video_uid=%s" % (self.siteUrl, stream_api, video_uid)
                headers = {
                    "User-Agent": self._ua,
                    "Referer": self.siteUrl + target_path,
                    "Accept": "application/json, text/plain, */*",
                    "Accept-Encoding": "gzip, deflate",
                    "X-Requested-With": "XMLHttpRequest",
                    "Connection": "keep-alive"
                }
                for retry in range(2):
                    try:
                        req = urllib.request.Request(dispatch_url, headers=headers)
                        with self.opener.open(req, timeout=8) as api_resp:
                            raw = api_resp.read()
                            if raw.startswith(b"\x1f\x8b"):
                                raw = gzip.decompress(raw)
                            json_data = json.loads(raw.decode("utf-8", errors="ignore"))
                            playlist = json_data.get("playlist", [])

                            cand_lines = []
                            for item in playlist:
                                u = str(item.get("url") or "").strip()
                                if not u or not u.startswith("http"):
                                    continue
                                u_low = u.lower()
                                if ".enc" in u_low or "player.centercdn.top" in u_low or "vcsocdp" in u_low:
                                    continue
                                cand_lines.append(u)

                            t1 = []
                            t2 = []
                            for u in cand_lines:
                                u_low = u.lower()
                                if "vcsheaye" in u_low or "vcmarrycdn" in u_low or "720p" in u_low or "1080p" in u_low:
                                    t1.append(u)
                                else:
                                    t2.append(u)

                            final_lines = t1 + t2
                            if final_lines:
                                if line_idx < len(final_lines):
                                    target_stream_url = final_lines[line_idx]
                                else:
                                    target_stream_url = final_lines[0]
                                break
                    except Exception:
                        pass
        else:
            target_stream_url = raw_id

        headers = {
            "User-Agent": self._ua,
            "Referer": self.targetOrigin + "/",
            "Origin": self.targetOrigin
        }

        return {
            "parse": 0,
            "jx": 0,
            "url": target_stream_url if target_stream_url else raw_id,
            "header": headers,
            "format": "hls"
        }

    def searchContent(self, key, quick, pg="1"):
        del quick
        if not key:
            return {"page": 1, "pagecount": 1, "limit": 0, "total": 0, "list": []}

        page_num = int(pg) if str(pg).isdigit() else 1
        encoded_key = urllib.parse.quote(str(key).strip())

        search_url = "/asian/zh-CN/search/videos/%s?page=%d" % (encoded_key, page_num)
        res = self._fetch(search_url, referer=self.siteUrl + "/asian/zh-CN")
        cards = self._parse_vod_list(res.get("text", ""))

        return {
            "page": page_num,
            "pagecount": page_num + 1 if len(cards) >= 12 else page_num,
            "limit": len(cards),
            "total": 9999,
            "list": cards
        }

    def action(self, action):
        if action == "toast":
            return {"msg": "当前有效主站: %s" % self.siteUrl}
        return {"msg": "ok"}

    def liveContent(self):
        return ""

    def localProxy(self, params):
        del params
        return [404, "text/plain; charset=utf-8", "Proxy not configured"]

    def destroy(self):
        self.options = {}

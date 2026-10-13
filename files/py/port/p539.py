#!/usr/bin/env python3

import sys
import re
import json
import ssl
import urllib.request
import urllib.parse
from urllib.parse import urlparse, quote, unquote, urljoin
import http.cookiejar
import gzip
import zlib

try:
    from base.spider import Spider as SpiderBase
except ImportError:
    class SpiderBase(object):
        pass


class Spider(SpiderBase):
    def init(self, extend=""):
        self.siteName = "黄果剧场"
        self.siteUrl = "https://huangguo.video"
        self.brandActor = "📺TG群: https://t.me/+3t5XRPPo9mlkZDRl"
        self.brandDirector = "📺ZakaTV"
        self._ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/27.0.1 Mobile/15E148 Safari/604.1"

        self.categories = [
            {"type_id": "1", "type_name": "MV/音乐剧"},
            {"type_id": "2", "type_name": "短片"},
            {"type_id": "3", "type_name": "连续剧"},
            {"type_id": "4", "type_name": "片段"}
        ]

        self.tag_options = [
            {"n": "全部", "v": ""},
            {"n": "都市", "v": "1"},
            {"n": "人妻", "v": "2"},
            {"n": "校园", "v": "5"},
            {"n": "职场", "v": "6"},
            {"n": "古风", "v": "7"},
            {"n": "乱伦", "v": "8"},
            {"n": "NTR", "v": "9"},
            {"n": "玄幻", "v": "40"}
        ]

        self._play_url_cache = {}

        self.ctx = ssl.create_default_context()
        self.ctx.check_hostname = False
        self.ctx.verify_mode = ssl.CERT_NONE

        self.cj = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cj),
            urllib.request.HTTPSHandler(context=self.ctx)
        )

    def getName(self):
        return self.siteName

    def isVideoFormat(self, url):
        low = (url or "").lower()
        return any(k in low for k in (".m3u8", ".mp4", ".flv", ".ts"))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        self._play_url_cache.clear()

    def _http_get(self, url, referer=None):
        if not url:
            return ""
        headers = {
            "User-Agent": self._ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": referer or (self.siteUrl + "/"),
            "Cookie": "hg_age=1",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive"
        }
        try:
            req = urllib.request.Request(url, headers=headers)
            with self.opener.open(req, timeout=5) as resp:
                raw = resp.read()
                enc = resp.headers.get("Content-Encoding", "").lower()
                if raw.startswith(b"\x1f\x8b") or enc == "gzip":
                    raw = gzip.decompress(raw)
                elif enc == "deflate":
                    try:
                        raw = zlib.decompress(raw)
                    except Exception:
                        raw = zlib.decompress(raw, -zlib.MAX_WBITS)
                try:
                    return raw.decode("utf-8")
                except Exception:
                    return raw.decode("latin1", errors="ignore")
        except Exception:
            return ""

    def _format_remarks(self, parts_list):
        clean_parts = [p.strip() for p in parts_list if p and p.strip()]
        if not clean_parts:
            return "ZakaTV"
        return "ZakaTV · " + " · ".join(clean_parts)

    def _parse_list(self, html):
        if not html:
            return []

        items = []
        seen = set()

        for art in re.finditer(
            r'<article class="(?:video-card|search-content-card)[^"]*">(.*?)</article>',
            html, re.S
        ):
            block = art.group(1)

            link_m = re.search(r'<a\s+href="(/(?:video|series)/[^"]+)"', block)
            if not link_m:
                continue
            path = link_m.group(1).strip()

            if path.startswith('/video/'):
                vid = 'video:' + path[len('/video/'):].strip('/')
            elif path.startswith('/series/'):
                vid = 'series:' + path[len('/series/'):].strip('/')
            else:
                continue

            if vid in seen:
                continue

            img_m = re.search(r'<img[^>]+src="([^"]+)"', block)
            cover = img_m.group(1).strip() if img_m else ""
            if cover.startswith('/'):
                cover = self.siteUrl + cover

            title = ""
            alt_m = re.search(r'<img[^>]+alt="([^"]*)"', block)
            if alt_m:
                title = alt_m.group(1).strip()
            if not title:
                t_m = re.search(
                    r'<p[^>]*class="[^"]*(?:text-cream|font-display)[^"]*"[^>]*>([^<]+)</p>',
                    block
                )
                if t_m:
                    title = t_m.group(1).strip()

            tag = ""
            tag_m = re.search(
                r'<span class="absolute bottom-2 right-2[^"]*">([^<]+)</span>', block)
            if tag_m:
                tag = tag_m.group(1).strip()

            sub = ""
            sub_m = re.search(
                r'<p class="mt-2[^"]*font-mono-meta[^"]*">(.*?)</p>', block, re.S)
            if sub_m:
                sub = re.sub(r'<[^>]+>', '', sub_m.group(1)).strip()

            meta_parts = []
            if tag:
                meta_parts.append(tag)
            if sub:
                meta_parts.append(sub)

            seen.add(vid)
            items.append({
                "vod_id": vid,
                "vod_name": title,
                "vod_pic": cover,
                "vod_remarks": self._format_remarks(meta_parts),
                "style": {"type": "rect", "ratio": 0.75}
            })

        return items

    def _extract_title(self, html):
        t_m = re.search(r'<title>(.*?)</title>', html, re.S)
        if t_m:
            title = t_m.group(1).strip()
            title = re.sub(r'\s*[-–|·]\s*黄果剧场.*$', '', title).strip()
            return title
        return ""

    def _extract_cover(self, html):
        m = re.search(r'<meta\s+property="og:image"\s+content="([^"]+)"', html)
        if m:
            return m.group(1).strip()
        m = re.search(r'data-poster="([^"]+)"', html)
        if m:
            pic = m.group(1).strip()
            return pic if pic.startswith('http') else self.siteUrl + pic
        return ""

    def _extract_intro(self, html):
        m = re.search(r'<meta\s+name="description"\s+content="([^"]+)"', html)
        return m.group(1).strip() if m else ""

    def _extract_hls(self, html):
        if not html:
            return ""
        m = re.search(r'data-hls="([^"]+)"', html)
        if m:
            url = m.group(1).strip()
            if url.startswith('//'):
                url = 'https:' + url
            elif url.startswith('/'):
                url = self.siteUrl + url
            return url
        return ""

    def _extract_episodes(self, html):
        if not html:
            return []
        eps = []
        seen = set()

        for m in re.finditer(
            r'<a[^>]+class="[^"]*ep-chip[^"]*"[^>]+href="(/video/[^"]+)"[^>]*>([^<]+)</a>',
            html
        ):
            path = m.group(1).strip()
            name = m.group(2).strip()
            ep_id = path[len('/video/'):].strip('/')
            if ep_id in seen:
                continue
            seen.add(ep_id)
            eps.append({"name": name, "ep_id": ep_id, "url": self.siteUrl + path})

        if not eps:
            for m in re.finditer(
                r'<a[^>]+href="(/video/[^"]+)"[^>]*class="[^"]*group[^"]*"[^>]*>(.*?)</a>',
                html, re.S
            ):
                path = m.group(1).strip()
                inner = m.group(2)
                ep_id = path[len('/video/'):].strip('/')
                if ep_id in seen:
                    continue
                nm = re.search(
                    r'<p[^>]*class="[^"]*font-display[^"]*"[^>]*>([^<]+)</p>', inner)
                name = nm.group(1).strip() if nm else ("第%d集" % (len(eps) + 1))
                seen.add(ep_id)
                eps.append({"name": name, "ep_id": ep_id, "url": self.siteUrl + path})

        return eps

    def _extract_series_url(self, html):
        m = re.search(r'data-series-url="([^"]+)"', html)
        if m:
            url = m.group(1).strip()
            return url if url.startswith('http') else self.siteUrl + url
        return ""

    def _resolve_mp4_from_m3u8(self, master_url, referer):
        if not master_url:
            return ""

        content = self._http_get(master_url, referer=referer)
        if not content:
            return ""

        m = re.search(r'https?://[^\s"\'<>\\]+\.mp4[^\s"\'<>\\]*', content)
        if m:
            return m.group(0)

        base = master_url.rsplit('/', 1)[0]
        sub_urls = []
        for line in content.split('\n'):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if line.startswith('http') and '.m3u8' in line:
                sub_urls.append(line)
            elif line.endswith('.m3u8'):
                sub_urls.append(base + '/' + line.lstrip('/'))

        priority = ['720p', '1080p', '480p', '360p']

        def score(u):
            for i, p in enumerate(priority):
                if p in u:
                    return i
            return 99

        sub_urls.sort(key=score)

        for sub in sub_urls:
            sub_content = self._http_get(sub, referer=referer)
            if not sub_content:
                continue
            m = re.search(r'https?://[^\s"\'<>\\]+\.mp4[^\s"\'<>\\]*', sub_content)
            if m:
                return m.group(0)
            sub_base = sub.rsplit('/', 1)[0]
            for line in sub_content.split('\n'):
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '.mp4' in line:
                    if line.startswith('http'):
                        return line
                    elif line.startswith('/'):
                        return self.siteUrl + line
                    else:
                        return sub_base + '/' + line
        return ""

    def homeContent(self, filter):
        filters = {
            "1": self._build_filters(),
            "2": self._build_filters(),
            "3": self._build_filters(),
            "4": self._build_filters(),
        }
        return {"class": self.categories, "filters": filters}

    def _build_filters(self):
        return [
            {
                "key": "rating",
                "name": "尺度",
                "value": [
                    {"n": "全部", "v": ""},
                    {"n": "安全", "v": "safe"},
                    {"n": "裸露", "v": "nude"},
                    {"n": "限制级", "v": "explicit"},
                ]
            },
            {
                "key": "tags",
                "name": "标签",
                "value": self.tag_options,
            },
            {
                "key": "sort",
                "name": "排序",
                "value": [
                    {"n": "最新发布", "v": "latest"},
                    {"n": "最热", "v": "hot"},
                ]
            },
        ]

    def homeVideoContent(self):
        html = self._http_get(self.siteUrl + "/videos")
        items = self._parse_list(html)
        return {"list": items[:20]}

    def categoryContent(self, tid, pg, filter, extend):
        try:
            page = max(1, int(pg or 1))
        except (TypeError, ValueError):
            page = 1

        ext = {}
        if isinstance(extend, dict):
            ext = extend
        elif isinstance(extend, str) and extend.strip():
            try:
                ext = json.loads(extend)
            except Exception:
                ext = {}

        params = ["category=" + str(tid)]
        if ext.get("rating"):
            params.append("rating=" + str(ext["rating"]))
        if ext.get("tags"):
            params.append("tags=" + str(ext["tags"]))
        if ext.get("sort"):
            params.append("sort=" + str(ext["sort"]))
        if page > 1:
            params.append("page=" + str(page))

        url = self.siteUrl + "/videos?" + "&".join(params)

        html = self._http_get(url)
        items = self._parse_list(html)

        pagecount = page + 1 if items else page
        m = re.search(r'共\s*(\d+)\s*部', html)
        if m:
            total = int(m.group(1))
            page_size = 20
            if total > 0:
                pagecount = (total + page_size - 1) // page_size

        return {
            "list": items,
            "page": page,
            "pagecount": pagecount,
            "limit": 20,
            "total": 999,
        }

    def searchContent(self, key, quick, pg="1"):
        try:
            page = max(1, int(pg or 1))
        except (TypeError, ValueError):
            page = 1
        kw = str(key or "").strip()
        if not kw:
            return {"list": [], "page": page, "pagecount": 1, "limit": 20, "total": 0}

        url = self.siteUrl + "/search?q=" + quote(kw)
        if page > 1:
            url += "&page=" + str(page)

        html = self._http_get(url)
        items = self._parse_list(html)

        return {
            "list": items,
            "page": page,
            "pagecount": page + 1 if items else page,
            "limit": 20,
            "total": len(items),
        }

    def detailContent(self, ids):
        raw = str(ids[0] if isinstance(ids, (list, tuple)) else ids).strip()
        if not raw:
            return {"list": []}

        if raw.startswith('video:'):
            kind, real_id = 'video', raw[len('video:'):]
        elif raw.startswith('series:'):
            kind, real_id = 'series', raw[len('series:'):]
        else:
            kind, real_id = 'video', raw

        url = "%s/%s/%s" % (self.siteUrl, kind, real_id)
        html = self._http_get(url)
        if not html:
            return {"list": []}

        title = self._extract_title(html) or real_id
        pic = self._extract_cover(html)
        intro = self._extract_intro(html)

        clean_pic = pic if (pic.startswith("http://") or pic.startswith("https://")) else ""

        play_urls = []

        if kind == 'series':
            eps = self._extract_episodes(html)
            for ep in eps:
                clean_name = str(ep['name']).replace('$', '').replace('#', '')
                play_urls.append("%s$%s" % (clean_name, ep['url']))
        else:
            series_url = self._extract_series_url(html)
            if series_url:
                shtml = self._http_get(series_url)
                eps = self._extract_episodes(shtml)
                if eps:
                    for ep in eps:
                        clean_name = str(ep['name']).replace('$', '').replace('#', '')
                        play_urls.append("%s$%s" % (clean_name, ep['url']))
            if not play_urls:
                vurl = self._extract_hls(html)
                if vurl:
                    play_urls.append("正片$%s" % vurl)
                else:
                    play_urls.append("正片$%s" % url)

        remarks = ("ZakaTV · 共%d集" % len(play_urls)) if play_urls else "ZakaTV"

        return {
            "list": [{
                "vod_id": raw,
                "vod_name": title,
                "vod_pic": clean_pic,
                "vod_bg": clean_pic,
                "vod_background": clean_pic,
                "vod_banner": clean_pic,
                "vod_actor": self.brandActor,
                "vod_director": self.brandDirector,
                "vod_content": intro,
                "vod_remarks": remarks,
                "vod_play_from": "Zaka专线" if play_urls else "",
                "vod_play_url": "#".join(play_urls),
            }]
        }

    def playerContent(self, flag, id, vipFlags):
        raw = str(id or "").strip()
        if not raw:
            return {"parse": 0, "url": ""}

        if raw in self._play_url_cache:
            cached = self._play_url_cache[raw]
            return {
                "parse": 0,
                "url": cached,
                "header": {
                    "User-Agent": self._ua,
                    "Referer": self.siteUrl + "/",
                }
            }

        final_url = ""

        if raw.startswith('http') and '/video/' in raw and not self.isVideoFormat(raw):
            html = self._http_get(raw)
            master = self._extract_hls(html)
            if master:
                mp4 = self._resolve_mp4_from_m3u8(master, referer=raw)
                if mp4:
                    final_url = mp4
                else:
                    play_stream = master
                    if ".m3u8" not in play_stream.lower() and ".mp4" not in play_stream.lower():
                        sep = "&" if "?" in play_stream else "?"
                        play_stream = play_stream + sep + "format=.m3u8"
                    self._play_url_cache[raw] = play_stream
                    return {
                        "parse": 0,
                        "url": play_stream,
                        "header": {
                            "User-Agent": self._ua,
                            "Referer": raw,
                            "Origin": self.siteUrl,
                            "Cookie": "hg_age=1",
                        }
                    }

        elif self.isVideoFormat(raw) and '.m3u8' in raw:
            mp4 = self._resolve_mp4_from_m3u8(raw, referer=self.siteUrl + "/")
            if mp4:
                final_url = mp4
            else:
                play_stream = raw
                if ".m3u8" not in play_stream.lower() and ".mp4" not in play_stream.lower():
                    sep = "&" if "?" in play_stream else "?"
                    play_stream = play_stream + sep + "format=.m3u8"
                return {
                    "parse": 0,
                    "url": play_stream,
                    "header": {
                        "User-Agent": self._ua,
                        "Referer": self.siteUrl + "/",
                        "Cookie": "hg_age=1",
                    }
                }

        elif self.isVideoFormat(raw) and '.mp4' in raw:
            final_url = raw

        if final_url:
            if ".m3u8" not in final_url.lower() and ".mp4" not in final_url.lower():
                sep = "&" if "?" in final_url else "?"
                final_url = final_url + sep + "format=.m3u8"
            self._play_url_cache[raw] = final_url
            return {
                "parse": 0,
                "url": final_url,
                "header": {
                    "User-Agent": self._ua,
                    "Referer": self.siteUrl + "/",
                }
            }

        return {
            "parse": 0,
            "url": raw,
            "header": {
                "User-Agent": self._ua,
                "Referer": self.siteUrl + "/",
                "Cookie": "hg_age=1",
            }
        }

    def localProxy(self, params):
        return [404, "text/plain; charset=utf-8", b"Proxy not configured"]

    def liveContent(self):
        return ""

    def action(self, action):
        return {"msg": "ok"}
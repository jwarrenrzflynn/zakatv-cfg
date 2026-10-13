#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import json
import base64
import html as _html
import urllib.request
import urllib.parse
import urllib.error
import ssl

try:
    from base.spider import Spider as SpiderBase
except ImportError:
    class SpiderBase(object):
        def getCache(self, key):
            return None
        def setCache(self, key, value):
            return "fail"
        def delCache(self, key):
            return "fail"
        def getProxyUrl(self):
            return "http://127.0.0.1:9978/proxy"

def format_remarks(brand="ZakaTV", meta=""):
    clean_meta = str(meta or "").strip()
    clean_meta = re.sub(r"[\r\n\t]+", " ", clean_meta).strip()
    if clean_meta:
        return "%s | %s" % (brand, clean_meta)
    return brand

class Spider(SpiderBase):
    def __init__(self):
        super(Spider, self).__init__()
        self.host = "https://fuwtrv.jxg2.buzz"
        self.home_url = self.host + "/jxg/"
        self.tgGroup = "https://t.me/+3t5XRPPo9mlkZDRl"
        self.brandActor = "📺TG群: https://t.me/+3t5XRPPo9mlkZDRl"
        self.brandDirector = "📺ZakaTV"
        self.brandName = "ZakaTV"
        self.cardStyle = {"type": "rect", "ratio": 1.78}
        self.ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        self.headers = {
            "User-Agent": self.ua,
            "Referer": self.host + "/",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        self.pic_referer = "@Referer=" + self.host + "/"
        self._proxy_port = 9978
        self.classes = [
            ("熟母少妇", "20"), ("网红直播", "21"), ("自拍偷拍", "22"),
            ("强奸乱伦", "23"), ("高清国产", "24"), ("韩国专区", "25"),
            ("日本有码", "26"), ("日本无码", "27"), ("欧美情色", "28"),
            ("动漫卡通", "29"), ("三级伦理", "30"),
        ]

    def _fetch(self, url, timeout=20):
        req = urllib.request.Request(url, headers=self.headers)
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                data = resp.read()
            for enc in ("utf-8", "gbk", "gb18030"):
                try:
                    return data.decode(enc)
                except Exception:
                    continue
            return data.decode("utf-8", "ignore")
        except Exception:
            return ""

    def _clean(self, s):
        if not s:
            return ""
        s = _html.unescape(s)
        s = re.sub(r"<[^>]+>", "", s)
        return s.strip()

    def _parse_cards(self, html):
        items = []
        chunks = re.split(r'<div class="feature-post', html)
        for ch in chunks[1:]:
            ch = ch[:6000]
            m = re.search(r'<a href="/(\d+)\.html"[^>]*title="([^"]*)"', ch)
            if m:
                vid, title = m.group(1), m.group(2)
            else:
                m2 = re.search(r'<a href="/(\d+)\.html"', ch)
                if not m2:
                    continue
                vid = m2.group(1)
                t = re.search(r'class="post-title"[^>]*>([^<]+)<', ch)
                title = t.group(1) if t else ""
            title = self._clean(title)
            pic = ""
            pm = re.search(r'data-original="([^"]+)"', ch)
            if pm:
                pic = pm.group(1)
            else:
                sm = re.search(r'src="(https?://[^"]+)"', ch)
                if sm and not sm.group(1).startswith("data:"):
                    pic = sm.group(1)
            raw_remark = ""
            rm = re.search(r'class="btn-l"[^>]*>\s*(?:<a[^>]*>)?([^<]+)', ch)
            if rm:
                raw_remark = self._clean(rm.group(1))[:16]

            remarks = format_remarks(self.brandName, raw_remark)

            if vid and title:
                if pic and not pic.startswith("data:") and "@Referer=" not in pic:
                    pic = pic + self.pic_referer
                items.append({
                    "vod_id": vid,
                    "vod_name": title,
                    "vod_pic": pic,
                    "vod_remarks": remarks,
                    "style": self.cardStyle
                })

        seen, out = set(), []
        for it in items:
            if it["vod_id"] not in seen:
                seen.add(it["vod_id"])
                out.append(it)
        return out

    def _parse_pagecount(self, html):
        m = re.search(r'>(\d+)\s*/\s*(\d+)<', html)
        if m:
            return m.group(1), m.group(2)
        return "1", "1"

    def getName(self):
        return self.brandName

    def getDependence(self):
        return []

    def isVideoFormat(self, url):
        u = (url or "").lower()
        if "/proxy?" in u or "key=hls/" in u:
            return True
        return any(k in u for k in (".m3u8", ".mp4", ".flv", ".mkv", ".ts"))

    def manualVideoCheck(self):
        return False

    def init(self, extend=""):
        return None

    def destroy(self):
        return None

    def homeContent(self, filter):
        html = self._fetch(self.home_url)
        classes = [{"type_id": tid, "type_name": name} for name, tid in self.classes]
        items = self._parse_cards(html)
        res = {"class": classes, "list": items[:72]}
        if filter:
            res["filters"] = {}
        return res

    def homeVideoContent(self):
        return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        del filter, extend
        try:
            page_no = int(pg)
        except Exception:
            page_no = 1

        if page_no <= 1:
            url = "%s/vodtype/%s.html" % (self.host, tid)
        else:
            url = "%s/vodtype/%s-%d.html" % (self.host, tid, page_no)
        html = self._fetch(url)
        items = self._parse_cards(html)
        page, pagecount = self._parse_pagecount(html)
        return {
            "list": items,
            "page": int(page),
            "pagecount": int(pagecount),
            "limit": 90,
            "total": 999999,
        }

    def detailContent(self, ids):
        raw_id = ids[0] if isinstance(ids, (list, tuple)) else str(ids)
        vid = str(raw_id).strip()
        url = "%s/%s.html" % (self.host, vid)
        html = self._fetch(url)
        title = ""
        m = re.search(r'<h1 class="heading-1"[^>]*>([^<]+)<', html)
        if m:
            title = self._clean(m.group(1))
        if not title:
            m2 = re.search(r'<title>([^-<]+)', html)
            title = self._clean(m2.group(1)) if m2 else vid
        pic = ""
        pm = re.search(r'(https?://[^"\']+/upload/vod/[^"\']+\.(?:jpg|jpeg|png|webp))', html)
        if pm:
            pic = pm.group(1) + self.pic_referer
        play_url = ""
        rm = re.search(r"const rawUrl = '([^']+\.m3u8[^']*)'", html)
        if rm:
            play_url = rm.group(1)
        else:
            fm = re.search(r'(https?://[^\s"\'$#]+\.m3u8(?:\?[^\s"\']*)?)', html)
            if fm:
                play_url = fm.group(1)

        raw_desc = ""
        desc_m = re.search(r'<div class="post-content"[^>]*>([\s\S]*?)</div>', html)
        if desc_m:
            raw_desc = self._clean(desc_m.group(1))

        full_desc = (
            "【🔥 官方交流群: %s】\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "%s"
        ) % (self.tgGroup, raw_desc)

        vod = {
            "vod_id": vid,
            "vod_name": title,
            "vod_pic": pic,
            "vod_actor": self.brandActor,
            "vod_director": self.brandDirector,
            "vod_remarks": format_remarks(self.brandName, "超清"),
            "vod_content": full_desc,
            "vod_play_from": "Zaka专线·去广告$$$Zaka专线·原画",
            "vod_play_url": ("正片$%s$$$正片$%s" % (self._proxy_url(play_url), play_url)) if play_url else "",
            "style": self.cardStyle
        }
        return {"list": [vod]}

    def searchContent(self, key, quick, pg="1"):
        del quick
        q = urllib.parse.quote(str(key or "").strip())
        url = "%s/s/index.html?wd=%s" % (self.host, q)
        html = self._fetch(url)
        items = self._parse_cards(html)
        page, pagecount = self._parse_pagecount(html)
        return {
            "list": items,
            "page": int(page),
            "pagecount": int(pagecount),
            "limit": 90,
            "total": 999999,
        }

    def _proxy_base(self):
        _fn = getattr(self, "getProxyUrl", None)
        if callable(_fn):
            try:
                _u = _fn(True)
                if _u:
                    return str(_u).split("?")[0].rstrip("/")
            except Exception:
                pass
        try:
            from base.spider import Spider as _BaseSpider
            _u = _BaseSpider.getProxyUrl(self, True)
            if _u:
                return str(_u).split("?")[0].rstrip("/")
        except Exception:
            pass
        try:
            from java.lang import Class
            _port = Class.forName("com.github.catvod.Proxy").getMethod("getPort", []).invoke(None, [])
            if _port:
                return "http://127.0.0.1:%s/proxy" % int(_port)
        except Exception:
            pass
        return "http://127.0.0.1:%s/proxy" % self._proxy_port

    def _proxy_url(self, url):
        _base = self._proxy_base()
        _enc = base64.b64encode(url.encode("utf-8")).decode("ascii")
        sep = "&" if "?" in _base else "?"
        return "%s%sdo=py&type=stream&url=%s" % (_base, sep, urllib.parse.quote(_enc, safe=""))

    def playerContent(self, flag, id, vipFlags):
        del flag, vipFlags
        raw_target = str(id or "").strip()
        _u = raw_target if ("/proxy?" in raw_target or raw_target.startswith("http://127.0.0.1")) else self._proxy_url(raw_target)
        return {
            "parse": 0,
            "playUrl": "",
            "url": _u,
            "header": {
                "User-Agent": self.ua,
                "Referer": self.host + "/",
            },
        }

    def _serve_clean_m3u8(self, url):
        try:
            body = self._hls_clean(url)
        except Exception:
            try:
                raw = self._fetch(url)
                base = url.rsplit("/", 1)[0] + "/"
                body = "\n".join(
                    urllib.parse.urljoin(base, l.strip()) if l.strip() and not l.strip().startswith("#") else l
                    for l in raw.splitlines()
                )
            except Exception:
                return [502, "text/plain", b"fetch failed"]
        data = body.encode("utf-8") if isinstance(body, str) else body
        return [200, "application/vnd.apple.mpegurl", data]

    def localProxy(self, param):
        if isinstance(param, dict):
            _p = dict(param)
        elif isinstance(param, str):
            try:
                _p = json.loads(param) if param.strip() else {}
            except Exception:
                _p = {}
            if not isinstance(_p, dict):
                _p = {}
        else:
            _p = {}

        _do = str(_p.get("do") or "")
        if _do == "local":
            _key = urllib.parse.unquote(str(_p.get("key") or _p.get("url") or _p.get("path") or ""))
            if _key.startswith("hls/"):
                _b64 = _key[4:].split("/")[0]
                try:
                    _url = base64.urlsafe_b64decode(_b64 + "=" * (-len(_b64) % 4)).decode("utf-8")
                except Exception:
                    return [400, "text/plain", b"bad key"]
                return self._serve_clean_m3u8(_url)
            return [404, "text/plain", b"bad key"]

        _url = urllib.parse.unquote(str(_p.get("url") or ""))
        if _url:
            try:
                _raw = base64.b64decode(_url).decode("utf-8")
                if _raw.startswith(("http://", "https://")):
                    _url = _raw
            except Exception:
                pass
        if _url and ".m3u8" in _url:
            return self._serve_clean_m3u8(_url)
        return [404, "text/plain", b"not found"]

    def _hls_clean(self, url):
        raw = self._fetch(url)
        if "#EXT-X-STREAM-INF" in raw:
            m = re.search(r'#EXT-X-STREAM-INF[^\n]*\n\s*([^\s#][^\n]*)', raw)
            if m:
                return self._hls_clean(urllib.parse.urljoin(url, m.group(1).strip()))
        base = url.rsplit("/", 1)[0] + "/"
        lines = raw.splitlines()
        seg_idx = []
        for i, l in enumerate(lines):
            s = l.strip()
            if s and not s.startswith("#"):
                seg_idx.append((i, s))

        dirs = {}
        for _, s in seg_idx:
            d = urllib.parse.urljoin(base, s).rsplit("/", 1)[0]
            dirs[d] = dirs.get(d, 0) + 1
        main_dir = max(dirs, key=dirs.get) if dirs else ""
        keep = set()
        dur = {}
        last_inf = None
        for i, l in enumerate(lines):
            s = l.strip()
            if s.startswith("#EXTINF"):
                m = re.match(r'#EXTINF:([\d.]+)', s)
                last_inf = float(m.group(1)) if m else None
            elif s and not s.startswith("#"):
                if last_inf is not None:
                    dur[i] = last_inf
                last_inf = None

        for i, s in seg_idx:
            if urllib.parse.urljoin(base, s).rsplit("/", 1)[0] != main_dir:
                continue
            if dur.get(i, 999) < 1.0:
                continue
            keep.add(i)

        out = []
        i = 0
        n = len(lines)
        while i < n:
            l = lines[i]
            s = l.strip()
            if s.startswith("#EXT-X-DISCONTINUITY"):
                i += 1
                continue
            if s.startswith("#EXT-X-MEDIA-SEQUENCE"):
                out.append("#EXT-X-MEDIA-SEQUENCE:0")
                i += 1
                continue
            if s.startswith("#EXT-X-KEY"):
                if "METHOD=NONE" in s:
                    i += 1
                    continue
                l = re.sub(r'URI="([^"]+)"',
                           lambda m: 'URI="%s"' % urllib.parse.urljoin(base, m.group(1)), l)
                out.append(l)
                i += 1
                continue
            if s.startswith("#EXTINF"):
                j = i + 1
                while j < n and not lines[j].strip():
                    j += 1
                if j < n and j in keep:
                    out.append(l)
                i += 1
                continue
            if s and not s.startswith("#"):
                if i in keep:
                    out.append(urllib.parse.urljoin(base, s))
                i += 1
                continue
            out.append(l)
            i += 1
        return "\n".join(out) + "\n"

    def liveContent(self):
        return ""

    def action(self, action):
        return {"msg": "ok"}
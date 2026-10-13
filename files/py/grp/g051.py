#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
狩都高速（a2609）TVBox Python 插件
====================================
站点：https://a2609.com
引擎：React SPA + Laravel（SSR内嵌 window.__MOVIE_APP__ JSON）
取流：POST /frontend/play/{id} 需 X-CSRF-TOKEN，返回 m3u8
出流域：speed.oris18.com
"""
import re
import json
import time
import codecs
import urllib.parse
import urllib.request
import ssl

# ==================== 配置 ====================
BASE = "https://a2609.com"
WATCH = "/watch/"
BROWSE = "/browse"
PLAY_API = "/frontend/play/"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
PAGE_SIZE = 24
PAGE_TTL = 300

# ==================== 全局状态 ====================
_cache = {}
_csrf = ""

# ==================== 工具 ====================
def _ent(s):
    if not s:
        return ""
    return (s.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
             .replace("&quot;", '"').replace("&#039;", "'")).strip()

def _px_img(url):
    if not url:
        return ""
    url = url.replace("\\/", "/")
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("/"):
        return BASE + url
    return url

def _extract_app(html):
    if not html or len(html) < 100:
        return {}
    m = re.search(r"window\.__MOVIE_APP__\s*=\s*JSON\.parse\('(.+?)'\)\s*;", html, re.S)
    if not m:
        return {}
    try:
        raw = m.group(1)
        decoded = codecs.decode(raw, "unicode_escape")
        return json.loads(decoded)
    except Exception:
        return {}

def _get_csrf(html):
    global _csrf
    if _csrf:
        return _csrf
    m = re.search(r'csrf-token"\s+content="([^"]+)"', html)
    if m:
        _csrf = m.group(1)
    return _csrf

def _fetch(url):
    if not url:
        return ""
    if url.startswith("//"):
        url = "https:" + url
    elif url.startswith("/"):
        url = BASE + url
    now = time.time()
    if url in _cache and now - _cache[url][0] < PAGE_TTL:
        return _cache[url][1]
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(url, headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            "Accept-Language": "zh-TW,zh;q=0.9",
            "Cookie": "age_confirmed=1",
        })
        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        if len(html) > 500:
            _cache[url] = (now, html)
        return html
    except Exception:
        return ""

def _fetch_play_url(vid):
    import http.cookiejar
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        opener.add_handler(urllib.request.HTTPSHandler(context=ctx))
        req = urllib.request.Request(BASE + WATCH + vid, headers={
            "User-Agent": UA,
            "Accept": "text/html,*/*;q=0.8",
            "Accept-Language": "zh-TW,zh;q=0.9",
        })
        with opener.open(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception:
        return ""
    csrf = _get_csrf(html)
    if not csrf:
        return ""
    try:
        data = b"{}"
        req = urllib.request.Request(BASE + PLAY_API + vid, data=data, headers={
            "User-Agent": UA,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-CSRF-TOKEN": csrf,
            "X-Requested-With": "XMLHttpRequest",
            "Referer": BASE + WATCH + vid,
        }, method="POST")
        with opener.open(req, timeout=15) as resp:
            body = resp.read().decode("utf-8", errors="replace")
        obj = json.loads(body)
        if obj.get("code") == 200:
            data_obj = obj.get("data", {})
            return data_obj.get("src", "")
        return ""
    except Exception:
        return ""

def _item_to_vod(item):
    return {
        "vod_id": item.get("id", ""),
        "vod_name": _ent(item.get("title", "")),
        "vod_pic": _px_img(item.get("poster", "")),
        "vod_remarks": _ent(item.get("number", "")),
    }

def _items_to_list(items):
    out = []
    if not items:
        return out
    for item in items:
        if isinstance(item, dict) and item.get("id"):
            out.append(_item_to_vod(item))
    return out

def _merge_arrays(*arrs):
    out = []
    seen = set()
    for arr in arrs:
        if not arr:
            continue
        for item in arr:
            if not isinstance(item, dict):
                continue
            vid = item.get("id", "")
            if vid and vid not in seen:
                seen.add(vid)
                out.append(item)
    return out

# ==================== TVBox Spider 类 ====================
class Spider:
    def init(self, extend=""):
        self.extend = extend or ""

    def homeContent(self, filter=False):
        cls = [
            {"type_id": "home", "type_name": "首页推荐"},
            {"type_id": "latest", "type_name": "最新上架"},
            {"type_id": "popular", "type_name": "热门排行"},
            {"type_id": "free", "type_name": "免费观看"},
        ]
        html = _fetch(BASE + "/")
        app = _extract_app(html)
        catalog = app.get("catalog", {})
        items = _merge_arrays(
            catalog.get("featured", []),
            catalog.get("popular", []),
            catalog.get("latest", []),
        )
        return json.dumps({
            "class": cls,
            "list": _items_to_list(items),
        }, ensure_ascii=False)

    def homeVideoContent(self):
        return self.categoryContent("home", "1")

    def categoryContent(self, tid, pg, filter=False, extend=None):
        page = max(1, int(pg) if pg else 1)
        if tid == "home":
            url = BASE + "/"
        elif tid == "latest":
            url = BASE + BROWSE + "?sort=latest&page=" + str(page)
        elif tid == "popular":
            url = BASE + BROWSE + "?sort=popular&page=" + str(page)
        elif tid == "free":
            url = BASE + BROWSE + "?section=free&page=" + str(page)
        else:
            url = BASE + BROWSE + "?page=" + str(page)
        html = _fetch(url)
        app = _extract_app(html)
        catalog = app.get("catalog", {})
        if tid == "home":
            items = _merge_arrays(
                catalog.get("featured", []),
                catalog.get("popular", []),
                catalog.get("latest", []),
            )
            total = len(items)
            last_page = 1
        else:
            items = catalog.get("items", [])
            total = catalog.get("total", 0)
            last_page = catalog.get("lastPage", page)
        return json.dumps({
            "page": page,
            "pagecount": last_page,
            "limit": PAGE_SIZE,
            "total": total,
            "list": _items_to_list(items),
        }, ensure_ascii=False)

    def detailContent(self, ids):
        vid = ids[0] if ids else ""
        if not vid:
            return json.dumps({"list": []}, ensure_ascii=False)
        html = _fetch(BASE + WATCH + vid)
        app = _extract_app(html)
        mv = app.get("movie")
        if not mv:
            return json.dumps({"list": []}, ensure_ascii=False)
        actors = mv.get("actors", [])
        actor_str = ",".join(_ent(a.get("name", "")) for a in actors if isinstance(a, dict))
        genres = mv.get("genres", [])
        type_str = ",".join(_ent(g) for g in genres if isinstance(g, str))
        vod = {
            "vod_id": vid,
            "vod_name": _ent(mv.get("title", "")),
            "vod_pic": _px_img(mv.get("poster", "")),
            "vod_remarks": _ent(mv.get("number", "")),
            "vod_year": str(mv.get("year", "")),
            "vod_area": "日本",
            "vod_content": _ent(mv.get("description", "")),
            "vod_actor": actor_str,
            "vod_type": type_str,
            "vod_play_from": "狩都高速",
            "vod_play_url": "立即播放$" + vid,
        }
        return json.dumps({"list": [vod]}, ensure_ascii=False)

    def searchContent(self, key, quick=False):
        if not key:
            return json.dumps({"list": []}, ensure_ascii=False)
        page = 1
        url = BASE + BROWSE + "?search=" + urllib.parse.quote(key) + "&page=" + str(page)
        html = _fetch(url)
        app = _extract_app(html)
        catalog = app.get("catalog", {})
        items = catalog.get("items", [])
        return json.dumps({
            "page": page,
            "pagecount": catalog.get("lastPage", page),
            "limit": PAGE_SIZE,
            "total": catalog.get("total", 0),
            "list": _items_to_list(items),
        }, ensure_ascii=False)

    def playerContent(self, flag, id, vipFlags=None):
        if not id or len(id) < 10:
            return ""
        m3u8 = _fetch_play_url(id)
        if not m3u8:
            return ""
        return json.dumps({
            "parse": 0,
            "url": m3u8,
            "header": "",
        }, ensure_ascii=False)

# ===== 自检 =====
if __name__ == "__main__":
    s = Spider()
    s.init()
    print("home:", s.homeContent()[:100])

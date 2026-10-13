#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================================
# AV01 · 蜂蜜影视（FongMi TV / TVBox）原生 Python 蜘蛛
#
# 站点：https://www.av01.media     （SPA + 同源 JSON 接口 /api/v1）
# 品牌：👑帝皇影视     TG群：t.me/+3t5XRPPo9mlkZDRl
#
# ───────────────────────── 真站实测（2026-09-23，逐条验过） ─────────────────────────
# 1) 列表 / 分类 / 详情 / 搜索 全部是公开 JSON 接口，**免鉴权**：
#      GET  /api/v1/videos/types/latest?page=&limit=
#      GET  /api/v1/videos/types/hottest?page=&limit=
#      POST /api/v1/videos/complex_search?lang=cn     ← 分类/片商/女优 + 排序，主筛选口
#      POST /api/v1/videos/search?lang=cn             ← 搜索
#      GET  /api/v1/videos/{id}
#      GET  /api/v1/videos/actress/{id} | maker/{id} | tag/{id}
#      GET  /api/v1/tags/by-video-count | makers/by-score | actresses/by-score
#
# 2) 取流是本源的**唯一技术难点**，实测结论：
#      · /api/v1/videos/{id}/manifest/master.m3u8 → 免票 200，出 3 条清晰度（360/720/1080）
#        但它的分片行是 CDN 绝对地址、**不带票据**，直取必 403
#      · CDN 域名 customers.iw01.xyz 上的 .m3u8 一律 403 "Forbidden Resource Pattern"
#        → 所以「把 CDN 清单地址直接丢给播放器」这条路是死的
#      · 分片（.m4s / init.mp4）带 ?access_token=<JWT> 才给 206，JWT 由
#        GET /api/v1/videos/{id}/cdn-access?token_v2=&expires=&ip= 签发（1 小时）
#      · 票据三段式：files.iw01.xyz/edge/geo.js?json → {token_v2, expires, ip}（10 分钟 ttl）
#
#    ⇒ 打法：源自己把清单拉回来，把 MAP/分片行改写成**走壳的本地代理**（127.0.0.1:9978/proxy），
#      代理里每次取分片现签现用 → 长片看到一半票据过期也能自动续，不会卡死。
#
# 3) 分类体系（两级）
#      一级 = 内容板块：最新 / 最热 / 分类片库 / 片商片库 / 女优片库
#      二级 = 板块内筛选：具体分类(标签) / 片商 / 女优 + 排序(最新/最热)
#    标签 1681 个、片商 879 个、女优 9717 个（口径：按片量/热度取头部，进筛选器）
#
# 4) 可选 ext（不配也能跑）：
#      {"img":1}      封面走本地代理（默认 0 = 直连 CDN，快；封面票据 30 分钟有效）
#      {"limit":24}   分类每页条数（默认 24）
#      {"lang":"cn"}  标题/简介语言，默认 cn（无翻译回退日文原名）
#
# 纯标准库实现（urllib），不依赖 requests / lxml，按手机壳真实条件可跑。
# ============================================================================

import sys
import os
import re
import ssl
import json
import time
import gzip
import zlib
import base64
import threading
import urllib.parse
import urllib.request

try:
    from base.spider import Spider as SpiderBase
except ImportError:  # 本机自测兜底，不改行为
    class SpiderBase(object):
        def getCache(self, key):
            return None

        def setCache(self, key, value):
            return "fail"

        def delCache(self, key):
            return "fail"

        def log(self, msg):
            try:
                print("[AV01] %s" % (msg,))
            except Exception:
                pass


# ───────────────────────────── 常量（真站实测值） ─────────────────────────────

BRAND = "👑帝皇影视"
TG_GROUP = "t.me/+3t5XRPPo9mlkZDRl"

SITE = "https://www.av01.media"
API = SITE + "/api/v1"
GEO_URL = "https://files.iw01.xyz/edge/geo.js?json"
CDN_HOST = "files.iw01.xyz"          # 封面/预览/雪碧图 host（带票据）
SEG_HOST_HINT = "customers.iw01.xyz"  # 分片 host（带票据），仅用于识别

UA = ("Mozilla/5.0 (Linux; Android 13; Pixel 6) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36")

BASE_HEADERS = {
    "User-Agent": UA,
    "Referer": SITE + "/jp",
    "Origin": SITE,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,ja;q=0.8",
    "Accept-Encoding": "gzip, deflate",
}

SORT_OPTIONS = [
    {"n": "最新上架", "v": "latest"},
    {"n": "最热播放", "v": "hottest"},
]

# 接口全挂时的兜底分类（真站实测的热门标签，保证筛选器不空）
FALLBACK_TAGS = [
    ("LADA破解无码", "3583787"), ("高清", "314590"), ("单体作品", "0"),
]


# ───────────────────────────── 小工具 ─────────────────────────────

_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE


def _q(v):
    return urllib.parse.quote(str(v or ""), safe="")


def _uq(v):
    return urllib.parse.unquote(str(v or ""))


def _pick_title(v):
    """标题：优先中文/所选语言翻译，回退原文。不脱敏、不改字。"""
    t = v.get("title_translations")
    if isinstance(t, dict):
        for k in ("cn", "tw", "hk"):
            if t.get(k):
                return str(t[k]).strip()
    return str(v.get("title") or "").strip()


def _pick_desc(v):
    d = v.get("description_translations")
    if isinstance(d, dict):
        for k in ("cn", "tw", "hk"):
            if d.get(k):
                return str(d[k]).strip()
    return str(v.get("description") or "").strip()


def _name_of(obj, lang="cn"):
    """女优/片商/标签名：带 cn 翻译就用翻译。"""
    if not isinstance(obj, dict):
        return ""
    t = obj.get("name_translations")
    if isinstance(t, dict) and t.get(lang):
        return str(t[lang]).strip()
    return str(obj.get("name") or "").strip()


def _hms(seconds):
    try:
        s = int(seconds or 0)
    except Exception:
        return ""
    if s <= 0:
        return ""
    h, r = divmod(s, 3600)
    m = r // 60
    if h:
        return "%d:%02d" % (h, m)
    return "%d分" % m


def _fmt_views(n):
    try:
        n = int(n or 0)
    except Exception:
        return ""
    if n >= 10000:
        return "%.1f万" % (n / 10000.0)
    return str(n)


# ───────────────────────────── 主体 ─────────────────────────────

class Spider(SpiderBase):

    def __init__(self):
        self.extend = ""
        self.limit = 24
        self.img_proxy = False
        self.lang = "cn"
        self._mem = {}          # 进程内缓存（宿主缓存不可用时的兜底）

    # ------------------------------ 生命周期 ------------------------------

    def init(self, extend=""):
        self.extend = extend or ""
        cfg = {}
        if self.extend:
            try:
                cfg = json.loads(self.extend) if isinstance(self.extend, str) else dict(self.extend)
            except Exception:
                m = re.search(r"\{.*\}", str(self.extend))
                if m:
                    try:
                        cfg = json.loads(m.group(0))
                    except Exception:
                        cfg = {}
        if isinstance(cfg, dict):
            try:
                self.limit = max(6, min(int(cfg.get("limit") or 24), 60))
            except Exception:
                pass
            self.img_proxy = bool(cfg.get("img"))
            if cfg.get("lang"):
                self.lang = str(cfg["lang"])
        self.headers = dict(BASE_HEADERS)
        self.log("init ok  limit=%s img_proxy=%s" % (self.limit, self.img_proxy))

    # ------------------------------ HTTP（纯标准库） ------------------------------

    def _http(self, url, headers=None, data=None, timeout=15, retry=1):
        h = dict(BASE_HEADERS)
        if headers:
            h.update({k: v for k, v in headers.items() if v is not None})
        body = None
        if data is not None:
            body = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode("utf-8")
            h["Content-Type"] = "application/json"
        last = None
        for _ in range(retry + 1):
            try:
                req = urllib.request.Request(url, data=body, headers=h)
                with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as r:
                    raw = r.read()
                    code = getattr(r, "status", 200) or 200
                enc = (h.get("Accept-Encoding") or "").lower()
                if raw[:2] == b"\x1f\x8b" and "gzip" in enc:
                    raw = gzip.decompress(raw)
                elif raw[:1] == b"x" and "deflate" in enc:
                    try:
                        raw = zlib.decompress(raw)
                    except Exception:
                        raw = zlib.decompress(raw, -zlib.MAX_WBITS)
                return code, raw
            except urllib.error.HTTPError as e:
                last = e
                try:
                    raw = e.read()
                except Exception:
                    raw = b""
                # 403/404 别重试，浪费用户时间；5xx 重试一次
                if e.code < 500:
                    return e.code, raw
            except Exception as e:
                last = e
            time.sleep(0.4)
        self.log("http fail %s (%s)" % (url[:110], last))
        return 0, b""

    def _api_json(self, path, data=None, timeout=15, retry=1):
        url = path if path.startswith("http") else (API + "/" + path.lstrip("/"))
        code, raw = self._http(url, data=data, timeout=timeout, retry=retry)
        if code != 200 or not raw:
            return None
        try:
            return json.loads(raw.decode("utf-8", "ignore"))
        except Exception:
            return None

    # ------------------------------ 缓存 ------------------------------

    def _cache_get(self, key):
        v = self._mem.get(key)
        if v and v[0] > time.time():
            return v[1]
        try:
            got = self.getCache(key)
        except Exception:
            got = None
        if isinstance(got, dict) and "av01" in got:
            return got["av01"]
        return None

    def _cache_set(self, key, val, ttl):
        self._mem[key] = (time.time() + ttl, val)
        try:
            self.setCache(key, {"av01": val, "expiresAt": int(time.time() + ttl)})
        except Exception:
            pass

    # ------------------------------ 票据（三段式） ------------------------------

    def _geo(self, force=False):
        """
        取播放/封面票据： files.iw01.xyz/edge/geo.js?json
        返回 {token_v2, expires, ip, access_token, ttl}
        ★ 票据按请求方 IP 绑定 —— 源跑在手机里，跟播放器同一个出口，所以能直接用。
        """
        key = "av01_geo"
        if not force:
            got = self._cache_get(key)
            if got:
                return got
        code, raw = self._http(GEO_URL, headers={"Referer": SITE + "/"}, timeout=12)
        if code != 200 or not raw:
            got = self._cache_get(key) or self._mem.get(key, (0, None))[1]
            return got
        try:
            d = json.loads(raw.decode("utf-8", "ignore"))
        except Exception:
            return None
        if not d.get("token_v2"):
            return None
        ttl = int(d.get("ttl") or 600)
        val = {
            "token_v2": d.get("token_v2"),
            "access_token": d.get("access_token"),
            "expires": str(d.get("expires") or ""),
            "ip": d.get("ip") or "",
            "r2_cover": bool(d.get("r2_cover")),
        }
        self._cache_set(key, val, max(60, min(ttl - 60, 540)))
        return val

    def _cdn_token(self, vid, force=False):
        """分片票据：/videos/{id}/cdn-access → JWT（实测 1 小时有效，sub 锁死该片路径前缀）"""
        key = "av01_cdn_%s" % vid
        if not force:
            got = self._cache_get(key)
            if got:
                return got
        g = self._geo()
        if not g:
            return None
        url = "%s/videos/%s/cdn-access?token_v2=%s&expires=%s&ip=%s" % (
            API, vid, _q(g.get("token_v2")), _q(g.get("expires")), _q(g.get("ip")))
        d = self._api_json(url, timeout=12)
        if not d or not d.get("access_token"):
            return None
        left = 3000
        try:
            left = max(120, int(d.get("expires_at") or 0) - int(time.time()) - 120)
        except Exception:
            pass
        self._cache_set(key, d["access_token"], min(left, 3300))
        return d["access_token"]

    def _with_token(self, url, vid, force=False):
        tok = self._cdn_token(vid, force=force)
        if not tok:
            return url
        base = re.sub(r"([?&])access_token=[^&]*", r"\1", url).rstrip("?&")
        return base + ("&" if "?" in base else "?") + "access_token=" + tok

    # ------------------------------ 封面 ------------------------------

    def _cover_url(self, vid):
        """封面真址（实测）：https://files.iw01.xyz/covers/{id}/800.webp?token_v2=&expires=&ip="""
        g = self._geo()
        if not g:
            return "https://static.av01.tv/media/videos/tmb/%s/1.jpg/format=jpeg/wlv=320" % vid
        return "https://%s/covers/%s/800.webp?token_v2=%s&expires=%s&ip=%s" % (
            CDN_HOST, vid, _q(g.get("token_v2")), _q(g.get("expires")), _q(g.get("ip")))

    def _pic(self, vid):
        if self.img_proxy:
            return self._proxy("img", {"vid": vid})
        return self._cover_url(vid)

    # ------------------------------ 本地代理地址 ------------------------------

    def _proxy_url(self):
        try:
            p = self.getProxyUrl()
        except Exception:
            p = None
        if not p:
            p = "http://127.0.0.1:9978/proxy?do=py"
        if "do=py" not in p:
            p = p + ("&" if "?" in p else "?") + "do=py"
        return p

    def _proxy(self, mode, extra=None):
        qs = ["av01=" + _q(mode)]
        for k, v in (extra or {}).items():
            qs.append("%s=%s" % (k, _q(v)))
        return self._proxy_url() + "&" + "&".join(qs)

    # ------------------------------ 列表/分类数据 ------------------------------

    def _card(self, v):
        if not isinstance(v, dict):
            return None
        vid = v.get("id")
        if not vid:
            return None
        rem = []
        if v.get("dvd_id"):
            rem.append(str(v["dvd_id"]))
        d = _hms(v.get("duration"))
        if d:
            rem.append(d)
        vw = _fmt_views(v.get("views"))
        if vw:
            rem.append(vw + "播放")
        return {
            "vod_id": str(vid),
            "vod_name": _pick_title(v) or str(v.get("dvd_id") or vid),
            "vod_pic": self._pic(vid),
            "vod_remarks": " · ".join(rem),
        }

    def _cards(self, videos):
        out = []
        for v in videos or []:
            c = self._card(v)
            if c:
                out.append(c)
        return out

    def _latest(self, pg, limit=None):
        d = self._api_json("videos/types/latest?page=%s&limit=%s" % (pg, limit or self.limit))
        return (d or {}).get("videos") or [], (d or {}).get("pagination") or {}

    def _hottest(self, pg, limit=None):
        d = self._api_json("videos/types/hottest?page=%s&limit=%s" % (pg, limit or self.limit))
        return (d or {}).get("videos") or [], (d or {}).get("pagination") or {}

    def _complex(self, pg, filters, sort_field):
        body = {
            "filters": filters or {"actress_logic": "or"},
            "pagination": {"page": int(pg or 1), "limit": self.limit},
            "sort": {"field": "hottest" if sort_field == "hottest" else "latest", "order": "desc"},
        }
        d = self._api_json("videos/complex_search?lang=%s" % _q(self.lang), data=body, timeout=20)
        return (d or {}).get("videos") or [], (d or {}).get("pagination") or {}

    # ------------------------------ 分类体系（两级） ------------------------------

    def _taxonomy(self):
        """
        筛选器数据源：标签(按片量) / 片商(按热度) / 女优(按热度)。
        三个接口并发打，结果缓存 6 小时；全挂就回退到内置兜底（不影响列表/搜索）。
        """
        got = self._cache_get("av01_tax")
        if got:
            return got

        box = {}

        def work(name, path, pick, cap):
            try:
                d = self._api_json(path, timeout=12)
                arr = []
                if isinstance(d, dict):
                    arr = d.get(pick) or []
                items = []
                for it in (arr or [])[:cap]:
                    if not isinstance(it, dict):
                        continue
                    nm = _name_of(it, self.lang) or _name_of(it)
                    if not nm or not it.get("id"):
                        continue
                    items.append({"n": nm, "v": str(it["id"])})
                if items:
                    box[name] = items
            except Exception:
                pass

        jobs = [
            ("tag", "tags/by-video-count?page=1&limit=200", "tags", 150),
            ("maker", "makers/by-score?page=1&limit=120", "makers", 100),
            ("actress", "actresses/by-score?page=1&limit=160", "actresses", 120),
        ]
        ths = []
        for name, path, pick, cap in jobs:
            t = threading.Thread(target=work, args=(name, path, pick, cap))
            t.daemon = True
            t.start()
            ths.append(t)
        for t in ths:
            t.join(timeout=15)

        tax = {
            "tag": [{"n": "全部", "v": ""}] + box.get("tag", [{"n": n, "v": v} for n, v in FALLBACK_TAGS]),
            "maker": [{"n": "全部", "v": ""}] + box.get("maker", []),
            "actress": [{"n": "全部", "v": ""}] + box.get("actress", []),
        }
        if box:
            self._cache_set("av01_tax", tax, 21600)
        return tax

    def _classes(self):
        return [
            {"type_id": "new", "type_name": "🆕 最新上架"},
            {"type_id": "hot", "type_name": "🔥 最热播放"},
            {"type_id": "tag", "type_name": "🏷️ 分类片库"},
            {"type_id": "maker", "type_name": "🏢 片商片库"},
            {"type_id": "actress", "type_name": "👩 女优片库"},
        ]

    def _filters(self):
        tax = self._taxonomy()
        sort_vals = [dict(x) for x in SORT_OPTIONS]
        out = {}
        out["new"] = [{"key": "s", "name": "排序", "value": sort_vals}]
        out["hot"] = [{"key": "s", "name": "排序", "value": sort_vals}]
        out["tag"] = [
            {"key": "t", "name": "分类", "value": tax["tag"]},
            {"key": "s", "name": "排序", "value": sort_vals},
        ]
        out["maker"] = [
            {"key": "m", "name": "片商", "value": tax["maker"]},
            {"key": "s", "name": "排序", "value": sort_vals},
        ]
        out["actress"] = [
            {"key": "a", "name": "女优", "value": tax["actress"]},
            {"key": "s", "name": "排序", "value": sort_vals},
        ]
        return out

    # ------------------------------ 宿主接口：首页 ------------------------------

    def homeContent(self, filter):
        try:
            vs, _ = self._latest(1, min(self.limit, 20))
        except Exception:
            vs = []
        return {
            "class": self._classes(),
            "filters": self._filters(),
            "list": self._cards(vs),
        }

    def homeVideoContent(self):
        try:
            vs, _ = self._latest(1, min(self.limit, 20))
        except Exception:
            vs = []
        return {"list": self._cards(vs)}

    # ------------------------------ 宿主接口：分类 ------------------------------

    def categoryContent(self, tid, pg, filter, extend):
        tid = str(tid or "new")
        try:
            pg = int(pg or 1)
        except Exception:
            pg = 1
        ext = extend if isinstance(extend, dict) else {}
        try:
            if isinstance(extend, str) and extend.strip().startswith("{"):
                ext = json.loads(extend)
        except Exception:
            ext = {}

        sort_field = str(ext.get("s") or "latest")

        try:
            if tid == "tag":
                f = {"actress_logic": "or"}
                if ext.get("t"):
                    f["tags"] = [int(ext["t"])]
                vs, pag = self._complex(pg, f, sort_field)
            elif tid == "maker":
                f = {"actress_logic": "or"}
                if ext.get("m"):
                    f["makers"] = [int(ext["m"])]
                vs, pag = self._complex(pg, f, sort_field)
            elif tid == "actress":
                f = {"actress_logic": "or"}
                if ext.get("a"):
                    f["included_actresses"] = [int(ext["a"])]
                vs, pag = self._complex(pg, f, sort_field)
            elif sort_field == "hottest":
                vs, pag = self._hottest(pg)
            else:
                vs, pag = self._latest(pg)
        except Exception as e:
            self.log("categoryContent err %s" % e)
            vs, pag = [], {}

        total = 0
        try:
            total = int(pag.get("total") or 0)
        except Exception:
            total = 0
        pagecount = 0
        try:
            pagecount = int(pag.get("totalPages") or 0)
        except Exception:
            pagecount = 0
        if not pagecount:
            pagecount = pg + (1 if vs else 0)
        return {
            "list": self._cards(vs),
            "page": pg,
            "pagecount": pagecount,
            "limit": self.limit,
            "total": total,
        }

    # ------------------------------ 宿主接口：详情 ------------------------------

    def detailContent(self, ids):
        if isinstance(ids, (list, tuple)):
            ids = ids[0] if ids else ""
        elif isinstance(ids, dict):
            ids = ids.get("id") or ids.get("vod_id") or ""
        vid = str(ids or "").strip()
        m = re.search(r"(\d{3,})", vid)
        vid = m.group(1) if m else vid
        if not vid:
            return {"list": []}
        d = self._api_json("videos/%s" % vid, timeout=15) or {}

        name = _pick_title(d) or ("AV01-%s" % vid)
        dvd = str(d.get("dvd_id") or "")
        actors = [_name_of(a, self.lang) or _name_of(a) for a in (d.get("actresses") or [])]
        actors = [a for a in actors if a]
        tags = [_name_of(t, self.lang) or _name_of(t) for t in (d.get("tags") or [])]
        tags = [t for t in tags if t]
        maker = ""
        mt = d.get("maker_translations")
        if isinstance(mt, dict) and mt.get(self.lang):
            maker = str(mt[self.lang]).strip()
        elif d.get("maker"):
            maker = str(d["maker"]).strip()

        dt = str(d.get("published_time") or d.get("uploaded_time") or "")
        year = dt[:4] if len(dt) >= 4 else ""

        content_lines = []
        if dvd:
            content_lines.append("番号：%s" % dvd)
        if maker:
            content_lines.append("片商：%s" % maker)
        if actors:
            content_lines.append("女优：%s" % "、".join(actors))
        if tags:
            content_lines.append("标签：%s" % "、".join(tags[:12]))
        if d.get("duration"):
            content_lines.append("时长：%s" % _hms(d.get("duration")))
        if d.get("views"):
            content_lines.append("播放：%s" % _fmt_views(d.get("views")))
        desc = _pick_desc(d)
        if desc:
            content_lines.append("")
            content_lines.append(desc)
        content_lines.append("")
        content_lines.append("%s  %s" % (BRAND, TG_GROUP))

        # 播放线路：拿 master 清单的真实分片档位来标（360P/720P/1080P...）
        entries = self._play_entries(vid, d)

        return {
            "list": [{
                "vod_id": vid,
                "vod_name": name,
                "vod_pic": self._pic(vid),
                "vod_year": year,
                "vod_area": "日本",
                "vod_remarks": (dvd + " · " if dvd else "") + (_hms(d.get("duration")) or ""),
                "vod_actor": "、".join(actors),
                "vod_director": str(d.get("director") or ""),
                "vod_content": "\n".join([x for x in content_lines if x is not None]),
                "vod_play_from": BRAND,
                "vod_play_url": "#".join(entries),
            }]
        }

    def _variants(self, vid):
        """
        master.m3u8（免票）→ [(清晰度标签, 变体文件名)]，高→低。
        实测三条：640x360 / 1280x720 / 1920x1080
        """
        url = "%s/videos/%s/manifest/master.m3u8" % (API, vid)
        code, raw = self._http(url, headers={"Accept": "*/*", "Referer": SITE + "/"}, timeout=15)
        if code != 200 or not raw:
            return []
        try:
            text = raw.decode("utf-8", "ignore")
        except Exception:
            return []
        out = []
        res, bw = "", ""
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("#EXT-X-STREAM-INF"):
                m = re.search(r"RESOLUTION=(\d+)x(\d+)", line)
                res = (m.group(2) + "P") if m else ""
                b = re.search(r"BANDWIDTH=(\d+)", line)
                bw = b.group(1) if b else ""
            elif not line.startswith("#"):
                label = res or ("%.1fM" % (int(bw) / 1000000.0) if bw else ("线路%d" % (len(out) + 1)))
                out.append({"label": label, "path": line, "res": res, "bw": bw})
                res, bw = "", ""
        return out

    def _probe_variant(self, vid, path):
        """
        单档可用性探测：拿该档清单的第一个分片试 1KB。
        ★ 实测有片子的高码档分片 CDN 直接 503（片子刚上、转码没齐），
          不探测就会点进去黑屏 —— 所以列表/播放都只摆**实测能取到字节**的档。
        """
        if not path:
            return False
        url = urllib.parse.urljoin(API + "/videos/%s/manifest/" % vid, path)
        code, raw = self._http(url, headers={"Accept": "*/*", "Referer": SITE + "/"}, timeout=15)
        if code != 200 or not raw:
            return False
        first = ""
        for line in raw.decode("utf-8", "ignore").splitlines():
            s = line.strip()
            if s and not s.startswith("#"):
                first = s
                break
        if not first:
            return False
        target = urllib.parse.urljoin(url, first)
        for attempt in (0, 1):
            if attempt:
                self._cdn_token(vid, force=True)
            t = self._with_token(target, vid, force=bool(attempt))
            c2, r2 = self._http(t, headers={
                "Accept": "*/*", "Referer": SITE + "/", "Range": "bytes=0-1023",
            }, timeout=20)
            if c2 in (200, 206) and len(r2) > 0:
                return True
            if c2 and 400 <= c2 < 500:
                return False     # 真没这片（401/403/404），别浪费第二次
        return False

    def _variants_usable(self, vid):
        """可用档位（实测能出字节的），高→低；全挂就原样返回，别把入口全掐死。"""
        key = "av01_varok_%s" % vid
        got = self._cache_get(key)
        if got:
            return got
        base = self._variants(vid)
        if not base:
            return []
        ok = [v for v in base if self._probe_variant(vid, v.get("path"))]
        res = ok or base
        # 档位从高到低排（BANDWIDTH 降序）
        try:
            res = sorted(res, key=lambda x: int(x.get("bw") or 0), reverse=True)
        except Exception:
            pass
        self._cache_set(key, res, 1800)
        return res

    def _play_entries(self, vid, detail=None):
        """
        播放条目：自动 + 各可用清晰度（实测过的档位）。
        id 约定： <vid>@0(自动/主清单)  <vid>@1..n(第 n 档，按高→低)
        """
        vs = self._variants_usable(vid)
        entries = ["▶ 自动（按网速）$%s@0" % vid]
        for i, v in enumerate(vs, 1):
            entries.append("%s$%s@%d" % (v.get("label") or ("线路%d" % i), vid, i))
        if len(entries) == 1:  # 主清单都没拿到：仍给一个入口，playerContent 里再试
            entries = ["▶ 立即播放$%s@0" % vid]
        return entries

    # ------------------------------ 宿主接口：搜索 ------------------------------

    def searchContent(self, key, quick, pg="1"):
        key = str(key or "").strip()
        if not key:
            return {"list": []}
        try:
            page = int(pg or 1)
        except Exception:
            page = 1
        body = {"query": key, "pagination": {"page": page, "limit": self.limit}}
        d = self._api_json("videos/search?lang=%s" % _q(self.lang), data=body, timeout=20)
        vs = (d or {}).get("videos") or []
        pag = (d or {}).get("pagination") or {}
        total = 0
        try:
            total = int(pag.get("total") or 0)
        except Exception:
            total = 0
        pagecount = 0
        try:
            pagecount = int(pag.get("totalPages") or 0)
        except Exception:
            pagecount = 0
        if not pagecount:
            pagecount = page + (1 if vs else 0)
        return {
            "list": self._cards(vs),
            "page": page,
            "pagecount": pagecount,
            "limit": self.limit,
            "total": total,
        }

    # ------------------------------ 宿主接口：播放 ------------------------------

    def playerContent(self, flag, id, vipFlags):
        raw = str(id or "").strip()
        vid, idx = raw, 0
        m = re.match(r"^(\d{3,})(?:@(\d+))?$", raw)
        if m:
            vid = m.group(1)
            idx = int(m.group(2) or 0)
        else:
            m2 = re.search(r"(\d{3,})", raw)
            if m2:
                vid = m2.group(1)

        if idx <= 0:
            url = self._proxy("master", {"vid": vid})
        else:
            url = self._proxy("var", {"vid": vid, "q": idx})

        return {
            "parse": 0,
            "playUrl": "",
            "url": url,
            "header": {
                "User-Agent": UA,
                "Referer": SITE + "/",
                "Origin": SITE,
            },
        }

    # ------------------------------ 宿主接口：本地代理 ------------------------------

    def localProxy(self, param):
        """
        壳每次播放/取图都会打 http://127.0.0.1:9978/proxy?do=py&av01=xxx...
        这里返回 [状态码, MIME, 内容]。三种模式：
          av01=master  主清单（把各档清晰度指向本代理的 var）
          av01=var     单档清单（把 MAP/分片指向本代理的 seg）
          av01=seg     分片（现签票据后直取，回流字节）
          av01=img     封面（可选，ext {"img":1} 时启用）
        """
        try:
            p = param if isinstance(param, dict) else {}
            if not p and isinstance(param, str):
                p = dict(urllib.parse.parse_qsl(param))
            mode = p.get("av01") or p.get("mode") or ""
            vid = str(p.get("vid") or "").strip()

            if mode == "master":
                return self._proxy_master(vid)
            if mode == "var":
                return self._proxy_var(vid, p.get("q"), p.get("u"))
            if mode == "seg":
                return self._proxy_seg(vid, p.get("u"))
            if mode == "img":
                return self._proxy_img(vid, p.get("u"))
            return [404, "text/plain; charset=utf-8", b"unknown mode"]
        except Exception as e:
            self.log("localProxy err %s" % e)
            return [500, "text/plain; charset=utf-8", str(e).encode("utf-8", "ignore")]

    def _proxy_master(self, vid):
        vs = self._variants_usable(vid)
        if not vs:
            return [502, "text/plain; charset=utf-8", b"no variants"]
        out = ["#EXTM3U", "#EXT-X-VERSION:3"]
        for i, v in enumerate(vs, 1):
            bw = int(v.get("bw") or 0) or 800000
            res = ""
            if v.get("res"):
                res = ",RESOLUTION=" + self._res_of(v)
            out.append("#EXT-X-STREAM-INF:PROGRAM-ID=1,BANDWIDTH=%d%s,CODECS=\"avc1.640028,mp4a.40.2\"" % (bw, res))
            out.append(self._proxy("var", {"vid": vid, "q": i}))
        return [200, "application/vnd.apple.mpegurl", ("\n".join(out) + "\n").encode("utf-8")]

    @staticmethod
    def _res_of(v):
        """把 '1080P' 补成 '1920x1080'（真站 master 里常见的 16:9 档位）。"""
        m = re.search(r"(\d+)x(\d+)", str(v.get("res") or ""))
        if m:
            return m.group(0)
        m = re.search(r"(\d+)P", str(v.get("label") or ""), re.I)
        if not m:
            return ""
        h = int(m.group(1))
        w = {360: 640, 480: 854, 720: 1280, 1080: 1920, 2160: 3840}.get(h, int(h * 16 / 9))
        return "%dx%d" % (w, h)

    def _proxy_var(self, vid, q, u):
        """把某一档清单拉回来（真址在 av01.media，免票），分片改走本代理。"""
        variants = self._variants_usable(vid)
        path = u
        try:
            qi = int(q or 1)
        except Exception:
            qi = 1
        if not path:
            if not variants:
                return [502, "text/plain; charset=utf-8", b"no variants"]
            qi = max(1, min(qi, len(variants)))
            path = variants[qi - 1].get("path")
        url = urllib.parse.urljoin(API + "/videos/%s/manifest/" % vid, path)
        code, raw = self._http(url, headers={"Accept": "*/*", "Referer": SITE + "/"}, timeout=20)
        if code != 200 or not raw:
            return [502, "text/plain; charset=utf-8", ("variant %s" % code).encode()]
        text = raw.decode("utf-8", "ignore")
        if "#EXTM3U" not in text:
            return [502, "text/plain; charset=utf-8", b"not m3u8"]

        out = []
        for line in text.replace("\r", "").split("\n"):
            s = line.strip()
            if not s:
                continue
            if s.startswith("#"):
                # EXT-X-MAP / EXT-X-KEY 的 URI= 也要改走代理
                if "URI=" in s:
                    def _rw(m):
                        return 'URI="%s"' % self._proxy("seg", {"vid": vid, "u": m.group(1)})
                    s = re.sub(r'URI="([^"]+)"', _rw, s)
                out.append(s)
                continue
            if s.lower().startswith("http") or "/" in s:
                out.append(self._proxy("seg", {"vid": vid, "u": s}))
            else:
                out.append(s)
        return [200, "application/vnd.apple.mpegurl", ("\n".join(out) + "\n").encode("utf-8")]

    def _proxy_seg(self, vid, u):
        """分片：带上现签的票据直取。票据过期自动换一张重试一次。"""
        target = _uq(u)
        if not target:
            return [400, "text/plain; charset=utf-8", b"no target"]
        if not target.lower().startswith("http"):
            # 相对地址：用片子路径补全
            base = "%s/videos/%s/manifest/" % (API, vid)
            target = urllib.parse.urljoin(base, target)
        for attempt in range(3):
            if attempt == 2:
                # 手机切网换 IP 的场景：连 geo 票据一起重签
                self._geo(force=True)
            url = self._with_token(target, vid, force=(attempt > 0))
            code, raw = self._http(url, headers={
                "Accept": "*/*",
                "Referer": SITE + "/",
                "Range": "bytes=0-",
            }, timeout=25)
            if code in (200, 206) and raw:
                mime = "video/mp4"
                if target.lower().endswith(".m3u8"):
                    mime = "application/vnd.apple.mpegurl"
                elif target.lower().endswith(".ts"):
                    mime = "video/mp2t"
                elif target.lower().endswith(".vtt"):
                    mime = "text/vtt"
                return [200, mime, raw]
            # 401/403 = 票据过期；5xx（实测高码档刚上架时会 503）= CDN 临时状态
            # 两种都换新票再试一次，别直接甩黑屏给用户
            if code and code < 500 and code not in (401, 403):
                break
        self.log("seg fail %s" % target[:110])
        return [502, "text/plain; charset=utf-8", ("segment %s" % code).encode()]

    def _proxy_img(self, vid, u):
        target = _uq(u) or self._cover_url(vid)
        code, raw = self._http(target, headers={"Accept": "image/*", "Referer": SITE + "/"}, timeout=15)
        if code != 200 or not raw:
            return [502, "text/plain; charset=utf-8", b"image fail"]
        mime = "image/jpeg"
        if raw[:4] == b"RIFF":
            mime = "image/webp"
        elif raw[:4] == b"\x89PNG":
            mime = "image/png"
        elif raw[:4] == b"GIF8":
            mime = "image/gif"
        return [200, mime, raw]

    # ------------------------------ 杂项 ------------------------------

    def action(self, action):
        return {"msg": "ok", "brand": BRAND, "tg": TG_GROUP}

    def isVideoFormat(self, url):
        return bool(re.search(r"\.(m3u8|mp4|m4s|ts)(\?|$)", str(url or ""), re.I))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        self._mem = {}

    def getName(self):
        return BRAND

    def getDependence(self):
        return []

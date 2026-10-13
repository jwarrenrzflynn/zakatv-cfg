# -*- coding: utf-8 -*-

import re
import json
import time
import socket
import ssl
import uuid as _uuid
import threading

try:
    import urllib2 as _urlreq
    from urllib import quote as _quote
    from urllib import unquote as _unquote
    from urllib import urlencode as _urlencode
    _PY2 = True
except ImportError:
    import urllib.request as _urlreq
    from urllib.parse import quote as _quote
    from urllib.parse import unquote as _unquote
    from urllib.parse import urlencode as _urlencode
    _PY2 = False

DEFAULT_ENTRY = "https://7maoduanju.com"
API_PATH = "/api/toc/v1"

UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")

PAGE_SIZE = 12
HTTP_TIMEOUT = 10
PLAY_TIMEOUT = 15
PLAY_PROBE_TIMEOUT = 4

BRAND_NAME = u"ZakaTV"
BRAND_ACTOR = u"📺TG群: https://t.me/+3t5XRPPo9mlkZDRl"
BRAND_DIRECTOR = u"📺ZakaTV"

_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                      r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

LINES = [
    ("10000000-0000-4000-8000-0000000000c0", u"热门短剧"),
    ("10000000-0000-4000-8000-000000000002", u"原创短剧"),
    ("10000000-0000-4000-8000-0000000000b0", u"真人短剧"),
    ("10000000-0000-4000-8000-000000000005", u"擦边短剧"),
    ("10000000-0000-4000-8000-0000000000b3", u"AI短剧"),
    ("10000000-0000-4000-8000-000000000003", u"AI漫剧"),
    ("10000000-0000-4000-8000-0000000000b1", u"AI魔改"),
    ("10000000-0000-4000-8000-0000000000b2", u"AI换脸"),
    ("10000000-0000-4000-8000-0000000000b4", u"影视综艺"),
]

def _u(s):
    if not s:
        return u""
    try:
        if _PY2 and isinstance(s, str):
            return _unquote(s).decode("utf-8", "replace")
        return _unquote(s)
    except Exception:
        return s if isinstance(s, type(u"")) else _s2(s)

def _s2(b):
    if b is None:
        return u""
    if isinstance(b, type(u"")):
        return b
    if isinstance(b, bytes):
        try:
            return b.decode("utf-8", "replace")
        except Exception:
            return b.decode("latin-1", "replace")
    try:
        return unicode(b)
    except Exception:
        return str(b)

def _to_int(v, d=0):
    try:
        return int(v)
    except Exception:
        return d

def format_remarks(brand, info=""):
    b = _s2(brand or BRAND_NAME)
    i = _s2(info).strip()
    if not i:
        return b
    return u"%s · %s" % (b, i)

class Spider(object):

    def __init__(self):
        self.ext_raw = ""
        self.host = DEFAULT_ENTRY
        self.use_proxy = False
        self.do_probe = True
        self._token = None
        self._token_t = 0
        self._dl_cache = {}
        self._lock = threading.RLock()
        self._probe_cache = {}

        self._ssl_ctx = None
        try:
            self._ssl_ctx = ssl.create_default_context()
            self._ssl_ctx.check_hostname = False
            self._ssl_ctx.verify_mode = ssl.CERT_NONE
        except Exception:
            pass

    def getDependence(self):
        return []

    def init(self, extend=""):
        ext = extend
        if isinstance(ext, (list, tuple)):
            ext = ext[0] if ext else ""
        if isinstance(ext, bytes):
            ext = ext.decode("utf-8", "replace")
        if not isinstance(ext, str) and not isinstance(ext, type(u"")):
            ext = "" if ext is None else str(ext)
        self.ext_raw = (ext or "").strip()
        txt = self.ext_raw
        if txt.startswith("{"):
            try:
                d = json.loads(txt)
            except Exception:
                d = None
            if isinstance(d, dict):
                h = _u(d.get("host") or d.get("url") or d.get("ext") or "")
                if h:
                    self.host = (h if h.startswith("http") else "https://" + h).rstrip("/")
                self.use_proxy = str(d.get("proxy") or "0") in ("1", "true", "True")
                self.do_probe = str(d.get("probe", "1")) not in ("0", "false", "False")
        elif txt.startswith("http"):
            self.host = txt.rstrip("/")
        return None

    def destroy(self):
        return None

    def manualVideoCheck(self):
        return False

    def isVideoFormat(self, url):
        u = _s2(url or "").lower()
        return (".m3u8" in u) or (".mp4" in u) or (".flv" in u) or (".ts" in u)

    def action(self, action):
        return {}

    def getName(self):
        return BRAND_NAME + u"·七猫"

    def isSearchable(self):
        return True

    def _http(self, url, data=None, ref=None, timeout=None, raw=False):
        if not url:
            return None
        url = _s2(url)
        to = timeout or HTTP_TIMEOUT
        try:
            req = _urlreq.Request(url, data=data)
        except Exception:
            return None
        req.add_header("User-Agent", UA)
        req.add_header("Accept", "application/json, text/plain, */*")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        req.add_header("Referer", ref or (self.host + "/"))
        req.add_header("Origin", self.host)
        resp = None
        try:
            if self._ssl_ctx and hasattr(_urlreq, "HTTPSHandler"):
                opener = _urlreq.build_opener(_urlreq.HTTPSHandler(context=self._ssl_ctx))
                resp = opener.open(req, timeout=to)
            else:
                resp = _urlreq.urlopen(req, timeout=to)
            body = resp.read()
        except Exception:
            return None
        finally:
            try:
                if resp:
                    resp.close()
            except Exception:
                pass
        if raw:
            return body
        return _s2(body)

    def _api(self, path, params=None, method="GET", body=None, token=None):
        url = self.host + API_PATH + path
        if params:
            bits = []
            for k in params:
                v = params[k]
                if v is None or v == "":
                    continue
                bits.append("%s=%s" % (_quote(_s2(k)), _quote(_s2(v))))
            if bits:
                url += "?" + "&".join(bits)
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8") if not _PY2 else json.dumps(body)
        hdr_url = url
        if token or method == "POST":
            try:
                req = _urlreq.Request(hdr_url, data=data)
            except Exception:
                return None
            req.add_header("User-Agent", UA)
            req.add_header("Accept", "application/json")
            req.add_header("Referer", self.host + "/")
            req.add_header("Origin", self.host)
            if data is not None:
                req.add_header("Content-Type", "application/json")
            if token:
                req.add_header("Authorization", "Bearer " + token)
            resp = None
            try:
                if self._ssl_ctx and hasattr(_urlreq, "HTTPSHandler"):
                    opener = _urlreq.build_opener(_urlreq.HTTPSHandler(context=self._ssl_ctx))
                    resp = opener.open(req, timeout=HTTP_TIMEOUT)
                else:
                    resp = _urlreq.urlopen(req, timeout=HTTP_TIMEOUT)
                txt = _s2(resp.read())
            except Exception:
                return None
            finally:
                try:
                    if resp:
                        resp.close()
                except Exception:
                    pass
        else:
            txt = self._http(hdr_url)
        if not txt:
            return None
        try:
            return json.loads(txt)
        except Exception:
            return None

    def _anon_token(self):
        now = time.time()
        with self._lock:
            if self._token and (now - self._token_t) < 1800:
                return self._token
        dev = str(_uuid.uuid4())
        r = self._api("/auth/device", method="POST", body={"deviceId": dev})
        tok = ""
        if isinstance(r, dict):
            tok = _s2(r.get("token") or "")
        with self._lock:
            self._token = tok or None
            self._token_t = now
        return self._token

    def _pic(self, url):
        u = _s2(url or "")
        if not u:
            return u""
        if u.startswith("//"):
            return "https:" + u
        return u.split("@Referer")[0].split("@User-Agent")[0].strip()

    def _card(self, item):
        d = item if isinstance(item, dict) else {}
        did = _s2(d.get("id") or "")
        title = _s2(d.get("title") or "")
        if not did or not title:
            return None
        eps = _to_int(d.get("episodeCount"), 0)
        free = _to_int(d.get("freeEpisodeCount"), 0)
        pay = _s2(d.get("payMode") or "")
        vip = bool(d.get("isVipBadge"))
        notes = []
        if eps > 0:
            notes.append(u"%d集" % eps)
        if vip or pay == "vip_only":
            if free < 9000:
                notes.append(u"免%d·VIP" % free)
            else:
                notes.append(u"VIP")
        elif free < 9000 and eps > 0:
            notes.append(u"免%d集" % free)
        
        info_str = u" · ".join(notes)
        remarks_badge = format_remarks(BRAND_NAME, info_str)
        pic_url = self._pic(d.get("coverUrl"))

        return {
            "vod_id": did,
            "vod_name": title,
            "vod_pic": pic_url,
            "vod_remarks": remarks_badge,
            "style": {"type": "rect", "ratio": 0.75}
        }

    def _cards(self, arr):
        out = []
        if not isinstance(arr, list):
            return out
        for it in arr:
            c = self._card(it)
            if c:
                out.append(c)
        return out

    def homeContent(self, filter=None):
        cats = []
        filt = {}
        sort_vals = [
            {"n": u"默认", "v": "default"},
            {"n": u"最新", "v": "latest"},
            {"n": u"最热", "v": "hot"},
        ]
        status_vals = [
            {"n": u"全部", "v": "all"},
            {"n": u"连载中", "v": "ongoing"},
            {"n": u"已完结", "v": "completed"},
        ]
        for tid, name in LINES:
            cats.append({"type_id": str(tid), "type_name": name})
            filt[str(tid)] = [
                {"key": "sort", "name": u"排序", "value": sort_vals},
                {"key": "status", "name": u"状态", "value": status_vals},
            ]
        return {"class": cats, "filters": filt}

    def homeVideoContent(self):
        d = self._api("/home")
        rows = []
        if isinstance(d, dict):
            for blk in (d.get("blocks") or []):
                if not isinstance(blk, dict):
                    continue
                cards = self._cards(blk.get("items"))
                if cards:
                    rows.extend(cards)
        seen = set()
        out = []
        for c in rows:
            if c["vod_id"] in seen:
                continue
            seen.add(c["vod_id"])
            out.append(c)
        return {"list": out}

    def categoryContent(self, tid, pg=1, filter=None, extend=None):
        tid_str = _s2(tid).strip()
        pg = _to_int(pg, 1) or 1
        offset = (pg - 1) * PAGE_SIZE
        params = {"line": tid_str, "offset": offset}
        
        flt = extend if isinstance(extend, dict) else {}
        so = _s2(flt.get("sort") or "")
        st = _s2(flt.get("status") or "")
        if so and so not in ("sort", "default"):
            params["sort"] = so
        if st and st != "all":
            params["status"] = st
            
        d = self._api("/browse", params)
        items = []
        has_more = False
        total = 0
        if isinstance(d, dict):
            items = self._cards(d.get("items"))
            has_more = bool(d.get("hasMore"))
            total = _to_int(d.get("total"), 0)
        return {
            "list": items,
            "page": pg,
            "pagecount": (pg + 1) if has_more else pg,
            "limit": PAGE_SIZE,
            "total": total if total else (pg * PAGE_SIZE + (1 if has_more else 0)),
        }

    def searchContent(self, key, quick=False, pg="1"):
        k = _s2(key).strip()
        if not k:
            return {"list": []}
        d = self._api("/search", {"q": k})
        return {"list": self._cards(d)}

    def _fetch_drama(self, did, force=False):
        now = time.time()
        with self._lock:
            hit = self._dl_cache.get(did)
            if hit and not force and (now - hit[0]) < 300:
                return hit[1], hit[2]
        d = self._api("/dramas/" + _quote(did))
        if not isinstance(d, dict):
            return "", []
        eps = []
        for e in (d.get("episodes") or []):
            if not isinstance(e, dict):
                continue
            eps.append({
                "id": _s2(e.get("id")),
                "index": _to_int(e.get("indexNo"), 0),
                "title": _s2(e.get("title")),
                "locked": bool(e.get("locked")),
                "seo": _s2(e.get("seoContentUrl")),
            })
        try:
            eps.sort(key=lambda x: x["index"])
        except Exception:
            pass
        prefix = ""
        for e in eps:
            m = re.match(r"(https?://[^/\s]+/7cat/[^/\s]+)/hls/", e["seo"])
            if m:
                prefix = m.group(1)
                break
        with self._lock:
            self._dl_cache[did] = (now, prefix, eps)
        return prefix, eps

    def _seo_url(self, prefix, index):
        if not prefix or index <= 0:
            return ""
        return "%s/hls/ep%02d/ep%02d.m3u8" % (prefix, index, index)

    def _probe(self, url, timeout=4):
        if not url:
            return False
        now = time.time()
        with self._lock:
            hit = self._probe_cache.get(url)
            if hit and (now - hit[0]) < 900:
                return hit[1]
        ok = False
        try:
            req = _urlreq.Request(url)
        except Exception:
            return False
        req.add_header("User-Agent", UA)
        req.add_header("Range", "bytes=0-1023")
        resp = None
        try:
            if self._ssl_ctx and hasattr(_urlreq, "HTTPSHandler"):
                opener = _urlreq.build_opener(_urlreq.HTTPSHandler(context=self._ssl_ctx))
                resp = opener.open(req, timeout=timeout)
            else:
                resp = _urlreq.urlopen(req, timeout=timeout)
            body = resp.read(2048)
            ok = (b"#EXTM3U" in body) or ("#EXTM3U" in _s2(body))
        except Exception:
            ok = False
        finally:
            try:
                if resp:
                    resp.close()
            except Exception:
                pass
        with self._lock:
            self._probe_cache[url] = (now, ok)
        return ok

    def _probe_many(self, urls, workers=4):
        res = {}
        if not urls:
            return res
        lock = threading.Lock()

        def work(u):
            r = self._probe(u)
            with lock:
                res[u] = r

        queue = list(urls)
        while queue:
            batch = queue[:workers]
            queue = queue[workers:]
            threads = []
            for u in batch:
                t = threading.Thread(target=work, args=(u,))
                try:
                    t.setDaemon(True)
                except Exception:
                    pass
                t.start()
                threads.append(t)
            for t in threads:
                t.join(timeout=8)
        return res

    def _scan_cover(self, prefix, eps):
        detail = {}
        if not prefix or not eps:
            return 0, detail
        idxs = sorted([e["index"] for e in eps if e["index"] > 0])
        if not idxs:
            return 0, detail
        points = set()
        points.add(idxs[-1])
        locked = [e["index"] for e in eps if e["locked"]]
        if locked:
            points.add(locked[0])
            points.add(locked[len(locked) // 2])
        points = sorted(p for p in points if p > 0)
        urls = [self._seo_url(prefix, p) for p in points]
        try:
            res = self._probe_many(urls, workers=4)
        except Exception:
            res = {}
        cover = 0
        for p in points:
            u = self._seo_url(prefix, p)
            detail[u] = res.get(u)
            if res.get(u) and p > cover:
                cover = p
        return cover, detail

    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        if isinstance(ids, (list, tuple)):
            did = _s2(ids[0])
        else:
            did = _s2(ids)
        did = did.split("|")[0].strip()
        if not did:
            return {"list": []}

        d = self._api("/dramas/" + _quote(did))
        if not isinstance(d, dict):
            return {"list": []}
        title = _s2(d.get("title") or "")
        prefix, eps = self._fetch_drama(did)
        if not eps:
            return {"list": []}

        cover = 10 ** 9
        if self.do_probe:
            try:
                cover, _detail = self._scan_cover(prefix, eps)
            except Exception:
                cover = 10 ** 9

        eps_url = []
        marked = (self.do_probe and cover > 0)
        for e in eps:
            idx = e["index"]
            u = e["seo"] or self._seo_url(prefix, idx)
            mark = u""
            if u and marked and idx <= cover:
                mark = u"✅ "
            nm = e["title"] or (u"第%d集" % idx)
            flag = "%s|%s|%d" % (did, e["id"], idx)
            eps_url.append(u"%s%s$%s" % (mark, nm, flag))

        line_names = [u"📺Zaka专线", u"⚡ 全集秒播"]
        play_from = "$$$".join(line_names)
        play_url = "#".join(eps_url)

        notes = []
        eps_n = _to_int(d.get("episodeCount"), len(eps))
        free = _to_int(d.get("freeEpisodeCount"), 0)
        if eps_n:
            notes.append(u"%d集" % eps_n)
        if free and free < 9000:
            notes.append(u"免%d集" % free)
        tags = d.get("tags")
        if isinstance(tags, list) and tags:
            notes.append(u"/".join([_s2(x) for x in tags[:3]]))
        
        info_str = u" · ".join(notes)
        remarks_badge = format_remarks(BRAND_NAME, info_str)
        
        desc = _s2(d.get("description") or u"ZakaTV超清短剧聚合，全网同步上新。")
        full_content = (
            u"【🔥 官方交流群: %s】\n"
            u"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            u"%s"
        ) % (BRAND_ACTOR, desc)

        clean_pic = self._pic(d.get("coverUrl"))

        vod = {
            "vod_id": did,
            "vod_name": title,
            "vod_pic": clean_pic,
            "vod_bg": clean_pic,
            "vod_background": clean_pic,
            "vod_banner": clean_pic,
            "vod_actor": BRAND_ACTOR,
            "vod_director": BRAND_DIRECTOR,
            "vod_year": "",
            "vod_area": u"",
            "vod_remarks": remarks_badge,
            "vod_content": full_content,
            "vod_play_from": play_from,
            "vod_play_url": "$$$".join([play_url, play_url]),
        }
        return {"list": [vod]}

    def _official_url(self, did, ep_id):
        tok = self._anon_token()
        if not tok:
            return ""
        r = self._api("/dramas/%s/episodes/%s/play" % (_quote(did), _quote(ep_id)), token=tok)
        if isinstance(r, dict):
            return _s2(r.get("playUrl") or "")
        return ""

    def _unwrap(self, flag, ids):
        cands = []
        for v in (ids, flag):
            if isinstance(v, (list, tuple)):
                for x in v:
                    cands.append(_s2(x))
            else:
                cands.append(_s2(v))
        weak = ""
        for raw in cands:
            if not raw:
                continue
            raw = raw.strip()
            if u"$$$" in raw:
                raw = raw.split(u"$$$", 1)[0].strip()
            if u"#" in raw and not raw.startswith(u"http"):
                raw = raw.split(u"#", 1)[0].strip()
            for _ in range(3):
                if u"$" in raw:
                    raw = raw.rsplit(u"$", 1)[1].strip()
            if not raw:
                continue
            if raw.startswith(u"http"):
                return u"", raw
            parts = raw.split(u"|")
            if len(parts) >= 2 and _UUID_RE.match(parts[0].strip()):
                return raw, u""
            if len(parts) >= 3:
                return raw, u""
            if _UUID_RE.match(parts[0].strip()) and not weak:
                weak = raw
                continue
            if not weak and u" " not in raw:
                weak = raw
        return weak, u""

    def playerContent(self, flag, ids, vipFlags=None):
        empty = {"parse": 0, "jx": 0, "playUrl": "", "url": "",
                 "header": {"User-Agent": UA}}
        raw, direct = self._unwrap(flag, ids)
        if direct:
            target = direct
        else:
            if not raw:
                return empty
            parts = raw.split("|")
            did = parts[0].strip() if len(parts) > 0 else ""
            ep_id = parts[1].strip() if len(parts) > 1 else ""
            idx = _to_int(parts[2], 0) if len(parts) > 2 else 0
            if not did:
                return empty

            prefix, eps = self._fetch_drama(did)
            target = ""
            for e in eps:
                if ep_id and e["id"] == ep_id:
                    if not idx:
                        idx = e["index"]
                    target = e["seo"] or self._seo_url(prefix, e["index"])
                    break
            if not target and eps:
                if not idx:
                    idx = eps[0]["index"]
                if not ep_id:
                    ep_id = eps[0]["id"]
                target = self._seo_url(prefix, idx)
            if not target:
                target = self._official_url(did, ep_id)
            if target and not self._probe(target, timeout=PLAY_PROBE_TIMEOUT):
                alt = self._official_url(did, ep_id)
                if alt:
                    target = alt

        if not target:
            return empty

        if ".m3u8" not in target.lower() and not any(k in target.lower() for k in (".mp4", ".flv", ".mkv", ".ts")):
            sep = "&" if "?" in target else "?"
            target = target + sep + "format=.m3u8"

        return {
            "parse": 0,
            "jx": 0,
            "playUrl": "",
            "url": target,
            "header": {
                "User-Agent": UA,
                "Referer": self.host + "/"
            }
        }

    def localProxy(self, param):
        return None

_spider = Spider()

def getDependence(): return []
def init(extend=""): return _spider.init(extend)
def homeContent(filter=None): return _spider.homeContent(filter)
def homeVideoContent(): return _spider.homeVideoContent()
def categoryContent(tid, pg=1, filter=None, extend=None): return _spider.categoryContent(tid, pg, filter, extend)
def searchContent(key, quick=False, pg="1"): return _spider.searchContent(key, quick, pg)
def detailContent(ids): return _spider.detailContent(ids)
def playerContent(flag, ids, vipFlags=None): return _spider.playerContent(flag, ids, vipFlags)
def localProxy(param): return None
def isVideoFormat(url): return _spider.isVideoFormat(url)
def isSearchable(): return True
def manualVideoCheck(): return False
def action(action): return _spider.action(action)
def getName(): return _spider.getName()
def destroy(): return _spider.destroy()
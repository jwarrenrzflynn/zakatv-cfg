# -*- coding: utf-8 -*-
"""
JAV Verse (javverse.com) — TVBox / WebHTV 四壳通用 Python 源
================================================================================
与 Java 侧 csp_ZakaJavverseAmns 同一套接口、同一套 tid 口径、同一套字段，两边可互校。

站点：Next.js 的 JAV 资料库 + 社区（作品 / 女优 / 类别 / 片商 / 番号系列 / 评分 / 磁力）
      数据面是 SSR 直出 HTML（没有公开 JSON 数据接口），播放面是两条自有线路。

路由（2026-10-17/18 实地探站，逐条实测）
  首页推荐   /works                                    24 张卡
  时间线     /discover?page=N                          48/页；view=upcoming 看未发售
  类别       /genres            → /genre/{id}?page=N   48/页（315 个）
  片商       /makers            → /maker/{id}?page=N   48/页
  女优       /actresses?view=all · /actresses/top250 → /actress/{id}?page=N
  番号系列   /code/{PREFIX}?page=N                     48/页
  搜索       /search?q={词}&type=all
  详情       /work/{workId}

播放（★ 两个参数缺一不可，这是最容易踩的坑）
  POST /api/video/sessions   {"workId":<数字>,"code":"MKMP-00751"}   线路1 → playlistUrl（多码率 HLS）
  POST /api/video/line2      {"workId":<数字>,"code":"MKMP-00751"}   线路2 → fileUrl（整段 mp4，1GB 级）
  · workId 必须是**数字**、code 必须是**DMM 形态**（来源编号那行，字母前缀+5 位数字）；
    只给一个或把 workId 写成字符串 → 400 {"error":"Missing workId or code"}。
  · 票绑浏览器：POST 会下发 Set-Cookie jav_verse_video_key（Path=/api/video）。
    主清单、子清单、每个分片都必须带它，否则 403 "Media ticket is not for this browser"。
  → 所以本插件在本机起一个只读转发口（仅 127.0.0.1），自己带票去取，m3u8 里的
    子清单/分片/KEY 全部改写成回环地址再交给壳。线路2 的 mp4 走 Range 透传（可拖动）。
  · 票有时效：过期/403 会自动重开一次会话换新票，不把死地址焊死。

CF：HTML 文档路径挂在 Cloudflare 托管挑战后面（机房出口必挡）。
    ext 里可给 {"gateway":"http://你的取页网关:端口"}（契约 /fetch?u=<url>），
    设备侧一般直连就过；被挡时配网关。
================================================================================
"""
import base64
import gzip
import json
import re
import socketserver
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.append('..')
try:
    from base.spider import Spider as _Base
except Exception:
    _Base = object

HOST = "https://javverse.com"
HOSTS = [HOST]

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

PAGE_SIZE = 48
DIR_TTL = 6 * 3600

# ---------------------------------------------------------------- 本机转发
RELAY_HOST = "127.0.0.1"
_RELAY_LOCK = threading.Lock()
_RELAY = {"port": 0}

# 播放票据（jav_verse_video_key），全局共享：中继线程也要用
_CK_LOCK = threading.Lock()
_PLAY = {"ck": "", "ts": 0.0, "wid": 0, "code": "", "line": 1}


def _b64e(s):
    return base64.urlsafe_b64encode(s.encode("utf-8")).decode("ascii").rstrip("=")


def _b64d(s):
    try:
        s = str(s or "")
        s += "=" * (-len(s) % 4)
        return base64.urlsafe_b64decode(s.encode("ascii")).decode("utf-8", "ignore")
    except Exception:
        return ""


def _relay_link(u, kind="auto"):
    if not u:
        return u
    p = _relay_port()
    if not p:
        return u
    tag = "m3u8" if kind == "hls" else "ts"
    return "http://%s:%d/p.%s?u=%s" % (RELAY_HOST, p, tag, _b64e(u))


def _relay_open(u, rng=""):
    hd = {
        "User-Agent": UA,
        "Referer": HOST + "/",
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "identity",
        "Connection": "close",
    }
    ck = _PLAY.get("ck") or ""
    if ck:
        hd["Cookie"] = ck
    if rng:
        hd["Range"] = rng
    req = urllib.request.Request(u, headers=hd)
    return urllib.request.urlopen(req, timeout=60)


def _relay_rewrite(txt, base):
    """m3u8 里所有子清单 / 分片 / KEY / MAP 地址 → 全部改回本机转发"""
    out = []
    next_is_pl = False
    for ln in (txt or "").splitlines():
        s = ln.strip()
        if not s:
            continue
        if s.startswith("#"):
            if 'URI="' in s:
                s = re.sub(r'URI="([^"]+)"',
                           lambda m: 'URI="%s"' % _relay_link(
                               urllib.parse.urljoin(base, m.group(1)), "ts"), s)
            out.append(s)
            next_is_pl = s.startswith("#EXT-X-STREAM-INF")
            continue
        target = urllib.parse.urljoin(base, s)
        # 多码率主清单里 STREAM-INF 的下一行是「子清单」，不是分片
        out.append(_relay_link(target, "hls" if next_is_pl else "ts"))
        next_is_pl = False
    return "\n".join(out) + "\n"


class _RelayHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _head(self, code, n, ctype, extra=None):
        try:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(n))
            self.send_header("Access-Control-Allow-Origin", "*")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
        except Exception:
            pass

    def _raw(self, code, body, ctype):
        try:
            self._head(code, len(body), ctype)
            if self.command != "HEAD":
                self.wfile.write(body)
        except Exception:
            pass

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        p = urllib.parse.urlparse(self.path)
        if p.path not in ("/p", "/p.m3u8", "/p.ts"):
            return self._raw(404, b"not found", "text/plain")
        target = _b64d((urllib.parse.parse_qs(p.query).get("u") or [""])[0])
        if not target.startswith("http"):
            return self._raw(400, b"bad target", "text/plain")

        rng = self.headers.get("Range") or ""
        try:
            r = _relay_open(target, rng)
            ctype = (r.headers.get("Content-Type") or "").lower()
            clen = r.headers.get("Content-Length")
            crange = r.headers.get("Content-Range")
            code = getattr(r, "status", 200) or 200
            head = r.read(7)
            if head != b"#EXTM3U":
                # 媒体分片 / mp4：边收边转，绝不整段进内存（1GB 的片子会直接爆）
                return self._stream(r, head, code, ctype, clen, crange)
            data = head + r.read()
        except urllib.error.HTTPError as e:
            # 票过期 → 重开会话换票再取一次
            try:
                wid, code_c, line = _PLAY.get("wid"), _PLAY.get("code"), _PLAY.get("line", 1)
                if wid and code_c:
                    _open_session(HOST, wid, code_c, line)
                    r = _relay_open(target, rng)
                    ctype = (r.headers.get("Content-Type") or "").lower()
                    clen = r.headers.get("Content-Length")
                    crange = r.headers.get("Content-Range")
                    code = getattr(r, "status", 200) or 200
                    head = r.read(7)
                    if head != b"#EXTM3U":
                        return self._stream(r, head, code, ctype, clen, crange)
                    data = head + r.read()
                else:
                    return self._raw(502, b"upstream %d" % e.code, "text/plain")
            except Exception:
                return self._raw(502, b"upstream fail", "text/plain")
        except Exception as _e:
            try:
                sys.stderr.write("[jv-relay] %s: %s\n" % (type(_e).__name__, _e))
            except Exception:
                pass
            return self._raw(502, b"upstream fail", "text/plain")

        if data[:7] == b"#EXTM3U" or "mpegurl" in ctype:
            body = _relay_rewrite(data.decode("utf-8", "ignore"), target).encode("utf-8")
            return self._raw(200, body, "application/vnd.apple.mpegurl")
        extra = {}
        if clen:
            extra["Content-Length"] = clen
        if crange:
            return self._raw_partial(data, ctype or "application/octet-stream", crange, clen)
        return self._raw(code, data, ctype or "video/mp2t")

    def _stream(self, r, first, code, ctype, clen, crange):
        """分片 / mp4 直转：先发头，再一块块搬，内存占用恒定"""
        try:
            self.send_response(code if code >= 200 else 200)
            self.send_header("Content-Type", ctype or "video/mp2t")
            if crange:
                self.send_header("Content-Range", crange)
            if clen:
                try:
                    self.send_header("Content-Length", str(int(clen) + 0))
                except Exception:
                    pass
            else:
                # 上游没给长度就靠 close 结束（播放器能吃，个别壳会警告）
                self.send_header("Connection", "close")
                self.close_connection = True
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            if self.command == "HEAD":
                return
            if first:
                self.wfile.write(first)
            while True:
                chunk = r.read(262144)
                if not chunk:
                    break
                self.wfile.write(chunk)
        except Exception:
            pass
        finally:
            try:
                r.close()
            except Exception:
                pass

    def _raw_partial(self, data, ctype, crange, clen):
        try:
            self.send_response(206)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Content-Range", crange)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)
        except Exception:
            pass


RELAY_ON = False          # 默认不走中继：CDN 对 Python 的 TLS 指纹限速（实测慢 8 倍）


def _relay_port():
    if not RELAY_ON:
        return 0
    if _RELAY["port"]:
        return _RELAY["port"]
    with _RELAY_LOCK:
        if _RELAY["port"]:
            return _RELAY["port"]
        try:
            class _Srv(socketserver.ThreadingMixIn, HTTPServer):
                daemon_threads = True
                allow_reuse_address = True

            srv = _Srv((RELAY_HOST, 0), _RelayHandler)
            _RELAY["port"] = srv.server_address[1]
            t = threading.Thread(target=srv.serve_forever, name="jv-relay", daemon=True)
            t.start()
            return _RELAY["port"]
        except Exception:
            _RELAY["port"] = 0
            return 0


# ---------------------------------------------------------------- HTTP
class _HTTP(object):
    """极简 HTTP：普通 GET（带 gzip）+ POST JSON（拿 Set-Cookie）"""

    def __init__(self, host=HOST, gateway=""):
        self.host = host
        self.gateway = (gateway or "").rstrip("/")

    def get(self, url, referer="", timeout=25):
        if not url:
            return ""
        if url.startswith("//"):
            url = "https:" + url
        if url.startswith("/"):
            url = self.host + url
        hd = {
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,ja;q=0.7",
            "Referer": referer or (self.host + "/"),
        }
        try:
            req = urllib.request.Request(url, headers=hd)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
                if (r.headers.get("Content-Encoding") or "").lower() == "gzip":
                    try:
                        raw = gzip.decompress(raw)
                    except Exception:
                        pass
                txt = raw.decode("utf-8", "ignore")
                if txt and "work-card" not in txt and "directory-row" not in txt \
                        and "portrait-tile" not in txt and len(txt) > 500:
                    # 可能是盾页 —— 走网关再试一次（配了才走）
                    if self.gateway:
                        g = self._gw(url, referer)
                        if g:
                            return g
                return txt
        except Exception:
            if self.gateway:
                return self._gw(url, referer)
            return ""

    def _gw(self, url, referer=""):
        try:
            q = "?u=" + urllib.parse.quote(url, safe="")
            if referer:
                q += "&r=" + urllib.parse.quote(referer, safe="")
            req = urllib.request.Request(self.gateway + "/fetch" + q,
                                         headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.read().decode("utf-8", "ignore")
        except Exception:
            return ""

    def post_json(self, url, obj, timeout=20):
        """返回 (文本, Set-Cookie 串)"""
        if url.startswith("/"):
            url = self.host + url
        data = json.dumps(obj).encode("utf-8")
        hd = {
            "User-Agent": UA,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Origin": self.host,
            "Referer": self.host + "/",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        try:
            req = urllib.request.Request(url, data=data, headers=hd, method="POST")
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read().decode("utf-8", "ignore")
                ck = []
                try:
                    for v in r.headers.get_all("Set-Cookie") or []:
                        pair = v.split(";")[0].strip()
                        if "=" in pair:
                            ck.append(pair)
                except Exception:
                    pass
                return body, "; ".join(ck)
        except urllib.error.HTTPError as e:
            try:
                return e.read().decode("utf-8", "ignore"), ""
            except Exception:
                return "", ""
        except Exception:
            return "", ""


def _open_session(host, wid, code, line=1):
    """开会话换票；返回响应 dict（失败给 {}）"""
    ep = "/api/video/line2" if line == 2 else "/api/video/sessions"
    body, ck = _HTTP(host).post_json(host + ep, {"workId": int(wid), "code": code})
    try:
        d = json.loads(body) if body.strip().startswith("{") else {}
    except Exception:
        d = {}
    with _CK_LOCK:
        if ck:
            _PLAY["ck"] = ck
        _PLAY["ts"] = time.time()
        _PLAY["wid"] = int(wid)
        _PLAY["code"] = code
        _PLAY["line"] = line
    return d


# ---------------------------------------------------------------- 解析
P_CARD_OPEN = re.compile(r'<a class="work-card[^"]*"[^>]*href="/work/(\d+)"')
P_IMG = re.compile(r'<img[^>]*src="([^"]+)"')
P_H3 = re.compile(r"<h3[^>]*>(.*?)</h3>", re.S)
P_PREFIX = re.compile(r"code-plate-prefix[^>]*>([^<]+)<")
P_NUM = re.compile(r"code-plate-number[^>]*>(.*?)</span>", re.S)
P_DATE = re.compile(r'work-card-bottom"[^>]*>\s*<span[^>]*>([^<]*)</span>')
P_TILE = re.compile(r'<a class="portrait-tile"[^>]*href="/actress/(\d+)"')
P_TILE_NAME = re.compile(r"upright-name[^>]*>(.*?)</span>", re.S)
P_H1 = re.compile(r"<h1[^>]*>(.*?)</h1>", re.S)
P_OG = re.compile(r'<meta property="og:image" content="([^"]+)"')
P_DTDD = re.compile(r"<dt[^>]*>(.*?)</dt>\s*<dd[^>]*>(.*?)</dd>", re.S)
P_CODE = re.compile(r"来源编号</dt>\s*<dd[^>]*>\s*([^<\s]+)\s*</dd>")
P_TAG = re.compile(r"<[^>]+>")
P_STILL = re.compile(r'<a class="still"[^>]*href="([^"]+)"')


def _text(h):
    if not h:
        return ""
    s = P_TAG.sub(" ", h)
    for a, b in (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                 ("&quot;", '"'), ("&#39;", "'"), ("<!-- -->", "")):
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", s).strip()


def _parse_cards(html):
    out = []
    if not html or len(html) < 200:
        return out
    for m in P_CARD_OPEN.finditer(html):
        end = html.find("</a>", m.end())
        if end < 0:
            break
        blk = html[m.end():end]
        try:
            pic = ""
            mi = P_IMG.search(blk)
            if mi:
                pic = mi.group(1)
            name = ""
            mh = P_H3.search(blk)
            if mh:
                name = _text(mh.group(1))
            code = ""
            mp, mn = P_PREFIX.search(blk), P_NUM.search(blk)
            if mp and mn:
                code = mp.group(1).strip() + "-" + _text(mn.group(1)).replace("-", "").strip()
            date = ""
            md = P_DATE.search(blk)
            if md:
                date = md.group(1).strip()
            show = name or ("作品 " + m.group(1))
            if code and code not in show:
                show = code + " " + show
            rem = " · ".join([x for x in (code, date) if x])
            out.append({"vod_id": m.group(1), "vod_name": show[:100],
                        "vod_pic": pic, "vod_remarks": rem})
        except Exception:
            continue
    return out


def _parse_tiles(html):
    out = []
    if not html or len(html) < 200:
        return out
    for m in P_TILE.finditer(html):
        end = html.find("</a>", m.end())
        if end < 0:
            break
        blk = html[m.end():end]
        try:
            pic = ""
            mi = P_IMG.search(blk)
            if mi:
                pic = mi.group(1)
            nm = ""
            mn = P_TILE_NAME.search(blk)
            if mn:
                nm = _text(mn.group(1))
            if not nm:
                ma = re.search(r'alt="([^"]+)"', blk)
                if ma:
                    nm = ma.group(1).strip()
            mc = re.search(r"([\d,]+)\s*部作品", blk)
            out.append({"vod_id": "a:" + m.group(1), "vod_name": nm or ("女优 " + m.group(1)),
                        "vod_pic": pic, "vod_remarks": (mc.group(1) + " 部") if mc else "",
                        "vod_tag": "folder"})
        except Exception:
            continue
    return out


class Spider(_Base):

    def __init__(self):
        self.host = HOST
        self.gateway = ""
        self._http = _HTTP(HOST, "")
        self._dir = {}

    # ---------------- 壳接口 ----------------
    def getName(self):
        return "JAV Verse"

    def init(self, extend=""):
        ext = {}
        if extend:
            try:
                ext = json.loads(extend) if isinstance(extend, str) else dict(extend)
            except Exception:
                ext = {}
        if not isinstance(ext, dict):
            ext = {}
        h = (ext.get("host") or "").strip()
        if h:
            if not h.startswith("http"):
                h = "https://" + h
            self.host = h.rstrip("/")
        self.gateway = (ext.get("gateway") or "").strip().rstrip("/")
        global RELAY_ON
        try:
            RELAY_ON = bool(int(ext.get("relay", 0)))
        except Exception:
            RELAY_ON = str(ext.get("relay", "")).lower() in ("1", "true", "on", "yes")
        self._http = _HTTP(self.host, self.gateway)
        _relay_port()
        return self

    def destroy(self):
        return None

    def isVideoFormat(self, url):
        return bool(url and (".m3u8" in url or ".mp4" in url))

    def manualVideoCheck(self):
        return False

    def localProxy(self, param):
        return None

    def _fetch(self, path):
        return self._http.get(path, referer=self.host + "/")

    # ---------------- 分类树 ----------------
    def _dir_list(self, kind, limit):
        hit = self._dir.get(kind)
        if hit and time.time() - hit[0] < DIR_TTL:
            return hit[1][:limit]
        html = self._fetch("/genres" if kind == "genre" else "/makers")
        rows = []
        for m in re.finditer(r'<a class="directory-row" href="/%s/([^"]+)">(.*?)</li>' % kind,
                             html or "", re.S):
            nm = re.search(r'directory-name">([^<]+)<', m.group(2))
            if nm:
                rows.append((m.group(1), _text(nm.group(1))))
        self._dir[kind] = (time.time(), rows)
        return rows[:limit]

    # ---------------- 首页 ----------------
    def homeContent(self, filter):
        cls = [("🔥 最新发售", "disc:new"), ("📅 未发售档期", "disc:up"),
               ("🎬 推荐作品", "works:rec"), ("👑 人气女优 Top250", "actresses:top250"),
               ("👩 全部女优", "actresses:all")]
        for gid, gname in self._dir_list("genre", 40):
            cls.append(("🏷 " + gname, "g:" + gid))
        for mid, mname in self._dir_list("maker", 30):
            cls.append(("🏢 " + mname, "m:" + mid))
        return {"class": [{"type_name": n, "type_id": i} for n, i in cls],
                "list": self._home_list()}

    def homeVideoContent(self):
        return {"list": self._home_list()}

    def _home_list(self):
        return _parse_cards(self._fetch("/discover")) or _parse_cards(self._fetch("/works"))

    # ---------------- 分类 ----------------
    def categoryContent(self, tid, pg, filter, extend):
        try:
            page = max(1, int(pg))
        except Exception:
            page = 1
        tid = tid or "disc:new"

        if tid in ("actresses:all", "actresses:top250"):
            path = "/actresses/top250" if tid.endswith("top250") else "/actresses?view=all"
            if page > 1:
                path += ("&" if "?" in path else "?") + "page=%d" % page
            lst = _parse_tiles(self._fetch(path))
            return {"page": page, "pagecount": page + 1 if len(lst) >= 24 else page,
                    "limit": 24, "total": page * 24, "list": lst}

        if tid.startswith("g:"):
            path = "/genre/" + tid[2:]
        elif tid.startswith("m:"):
            path = "/maker/" + tid[2:]
        elif tid.startswith("a:"):
            path = "/actress/" + tid[2:]
        elif tid.startswith("code:"):
            path = "/code/" + tid[5:]
        elif tid == "disc:up":
            path = "/discover?view=upcoming"
        elif tid == "works:rec":
            path = "/works"
        else:
            path = "/discover"
        if page > 1:
            path += ("&" if "?" in path else "?") + "page=%d" % page

        lst = _parse_cards(self._fetch(path))
        return {"page": page,
                "pagecount": page + 1 if len(lst) >= PAGE_SIZE else page,
                "limit": PAGE_SIZE,
                "total": page * PAGE_SIZE + 1 if len(lst) >= PAGE_SIZE else (page - 1) * PAGE_SIZE + len(lst),
                "list": lst}

    # ---------------- 详情 ----------------
    def detailContent(self, ids):
        vid = ids[0]
        if vid.startswith("a:"):
            nm = self._actress_name(vid[2:])
            return {"list": [{"vod_id": vid, "vod_name": nm or ("女优 " + vid[2:]),
                              "vod_content": "女优作品墙 · 点播放看全部作品",
                              "vod_play_from": "作品列表", "vod_play_url": "全部作品$" + vid}]}

        html = self._fetch("/work/" + vid)
        mh = P_H1.search(html or "")
        title = _text(mh.group(1)) if mh else ""
        mc = P_CODE.search(html or "")
        code = mc.group(1).strip() if mc else ""
        mp = P_OG.search(html or "")
        pic = mp.group(1) if mp else ""

        facts = {}
        for m in P_DTDD.finditer(html or ""):
            k = _text(m.group(1))
            v = _text(m.group(2))
            if "发售" in k:
                facts["release"] = v
            elif "出演" in k:
                facts["actors"] = v
            elif "时长" in k:
                facts["dur"] = v
            elif "导演" in k:
                facts["director"] = v
            elif "制作片商" in k:
                facts["maker"] = v
            elif "厂牌" in k:
                facts["label"] = v
            elif "系列" in k:
                facts["series"] = v
            elif "类别" in k:
                facts["genres"] = v

        rel = facts.get("release", "")
        rem = " · ".join([x for x in (code, rel, facts.get("dur", "").replace(" 分钟", "分")) if x])

        lines = ["番号：%s" % (code or "—")]
        for k, label in (("release", "发售"), ("dur", "时长"), ("actors", "出演"),
                         ("director", "导演"), ("maker", "片商"), ("label", "厂牌"),
                         ("series", "系列"), ("genres", "类别")):
            if facts.get(k):
                lines.append("%s：%s" % (label, facts[k]))

        mag = self._magnets(vid)
        if mag:
            lines.append("")
            lines.append("--- 磁力链接 ---")
            lines.extend(mag)

        stills = [m.group(1) for m in P_STILL.finditer(html or "")][:8]
        if stills:
            lines.append("")
            lines.append("--- 剧照 ---")
            lines.extend(stills)

        vod = {
            "vod_id": vid,
            "vod_name": title or ("作品 " + vid),
            "vod_pic": pic,
            "type_name": facts.get("genres", "").replace(" ", " · "),
            "vod_year": rel[:4] if len(rel) >= 4 else "",
            "vod_area": "日本",
            "vod_actor": facts.get("actors", ""),
            "vod_director": facts.get("director", ""),
            "vod_remarks": rem,
            "vod_content": "\n".join(lines),
        }
        if code:
            vod["vod_play_from"] = "🚀 线路1$$$🔁 线路2"
            vod["vod_play_url"] = ("正片$%s|%s|1" % (vid, code)) + "$$$" + ("正片$%s|%s|2" % (vid, code))
        else:
            vod["vod_play_from"] = "JAV Verse"
            vod["vod_play_url"] = "信息页$%s/work/%s" % (self.host, vid)
        return {"list": [vod]}

    def _actress_name(self, aid):
        html = self._fetch("/actress/" + aid)
        m = P_H1.search(html or "")
        return _text(m.group(1)) if m else ""

    def _magnets(self, vid):
        try:
            t = self._http.get(self.host + "/api/works/%s/magnets" % vid,
                               referer=self.host + "/work/" + vid)
            if not t or '"items"' not in t:
                return []
            d = json.loads(t)
            out = []
            for it in (d.get("items") or [])[:8]:
                mag = it.get("magnet") or ""
                if len(mag) < 20:
                    continue
                out.append("· %s  [%s]" % (it.get("title") or "", it.get("size") or ""))
                out.append(mag)
            return out
        except Exception:
            return []

    # ---------------- 搜索 ----------------
    def searchContent(self, key, quick, pg="1"):
        q = urllib.parse.quote((key or "").strip(), safe="")
        lst = _parse_cards(self._fetch("/search?q=%s&type=all" % q))
        if not lst:
            lst = _parse_tiles(self._fetch("/search?q=%s&type=actresses" % q))
        return {"list": lst}

    # ---------------- 播放 ----------------
    def playerContent(self, flag, id, vipFlags):
        header = {"User-Agent": UA, "Referer": self.host + "/"}
        try:
            sp = (id or "").split("|")
            if len(sp) < 3:
                return {"parse": 0, "url": "", "header": header, "msg": "播放参数不完整，回详情页重试"}
            wid = int(sp[0])
            code = sp[1].strip()
            line = 2 if sp[2].strip() == "2" else 1

            d = _open_session(self.host, wid, code, line)
            if not d:
                return {"parse": 0, "url": "", "header": header, "msg": "取流失败，稍后重试"}
            pu = d.get("playlistUrl") or ""
            fu = d.get("fileUrl") or ""
            if not pu and not fu:
                return {"parse": 0, "url": "", "header": header,
                        "msg": d.get("error") or "没取到播放地址"}

            abs_url = (pu or fu)
            if abs_url.startswith("/"):
                abs_url = self.host + abs_url

            u = abs_url
            if RELAY_ON:
                u = _relay_link(abs_url, "hls" if pu else "ts") or abs_url
            ck = _PLAY.get("ck") or ""
            if ck:
                header["Cookie"] = ck
            return {"parse": 0, "url": u, "header": header}
        except Exception as e:
            return {"parse": 0, "url": "", "header": header, "msg": "播放异常：%s" % type(e).__name__}

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""成人俱乐部（18hub）TVBox Python 插件 · 纯标准库 · 播放地址base64编码"""
import json, re, sys, base64, urllib.request, urllib.parse, http.server, threading

BASE = "https://18hub.cc"
UA = "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 Chrome/131.0.0.0 Mobile Safari/537.36"
PAGE_SIZE = 35

CLASSES = [
    ("国产乱伦", "guochanab"), ("主播秀色", "zhuboa"), ("丝袜OL", "siwa"),
    ("强奸乱伦", "qiangjianb"), ("国产SM", "guochanad"), ("网曝系列", "wangpu"),
    ("精品推荐", "jingpin"), ("国产人妻", "guochanaf"), ("国产丝袜", "guochanah"),
    ("中文字幕", "zhongwenb"), ("性感人妻", "xinggan"), ("日本无码", "ribenak"),
    ("自拍偷拍", "zipaib"), ("日本片商", "ribenam"), ("探花嫖娼", "tanhuaa"),
    ("日本有码", "ribenar"), ("麻豆传媒", "madou"), ("卡通动漫", "katonga"),
    ("同性恋", "tongxing"),
]

def _http(url, ref=""):
    headers = {"User-Agent": UA, "Referer": ref or BASE + "/",
               "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
               "Accept-Language": "zh-CN,zh;q=0.9"}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read().decode("utf-8", errors="ignore")
    except Exception:
        return ""

def _ent(s):
    if not s: return ""
    s = re.sub(r"&#x([0-9a-fA-F]+);", lambda m: chr(int(m.group(1), 16)), s)
    s = re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))), s)
    return s.strip()

def _first(s, pat):
    m = re.search(pat, s, re.I | re.S)
    return m.group(1).strip() if m else ""

def _cards(html):
    out = []
    seen = set()
    for m in re.finditer(r'<a[^>]*href="(/video/([a-z0-9]+)\.html)"[^>]*>(.*?)</a>', html, re.S):
        vid = m.group(2)
        if not vid or len(vid) < 10 or vid in seen: continue
        seen.add(vid)
        body = m.group(3)
        name = _ent(_first(body, r'(?:data-cover-src|alt)="([^"]+)"')) or _ent(_first(body, r'<b[^>]*>([^<]+)</b>'))
        if not name: name = _ent(_first(body, r'title="([^"]+)"'))
        if not name: name = _ent(re.sub(r"<[^>]+>", "", body).strip()) or vid
        pic = _first(body, r'(?:data-cover-src|data-src|data-original|src)="([^"]+\.(?:jpg|jpeg|png|webp)(?:\?[^"]*)?)"')
        if pic and pic.startswith("//"): pic = "https:" + pic
        elif pic and pic.startswith("/"): pic = BASE + pic
        out.append({"vod_id": vid, "vod_name": name, "vod_pic": pic, "vod_remarks": "在线"})
    return out

class _Relay:
    def __init__(self):
        self.port = 0
        self.server = None
        self._start()

    def _start(self):
        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def do_GET(self):
                qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                typ = qs.get("type", [""])[0]
                url = qs.get("u", [""])[0]
                ref = qs.get("r", [""])[0]
                if not url:
                    self.send_response(404); self.end_headers(); return
                try:
                    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": ref or BASE + "/"})
                    with urllib.request.urlopen(req, timeout=30) as r:
                        data = r.read()
                        ctype = r.headers.get("Content-Type", "application/octet-stream")
                    if typ == "hls":
                        text = data.decode("utf-8", errors="ignore")
                        if "#EXTM3U" not in text:
                            self.send_response(502); self.end_headers(); return
                        out = []
                        for line in text.split("\n"):
                            t = line.strip()
                            if t and t[0] != "#":
                                a = urllib.parse.urljoin(url, t)
                                if t.lower().endswith(".m3u8"):
                                    out.append(f"http://127.0.0.1:{self.server.server_port}/?type=hls&u={urllib.parse.quote(a)}&r={urllib.parse.quote(ref)}")
                                else:
                                    out.append(f"http://127.0.0.1:{self.server.server_port}/?type=seg&u={urllib.parse.quote(a)}&r={urllib.parse.quote(ref)}")
                            elif t.startswith("#EXT-X-KEY"):
                                um = re.search(r'URI="([^"]+)"', t)
                                if um and not um.group(1).startswith("http"):
                                    a = urllib.parse.urljoin(url, um.group(1))
                                    nu = f"http://127.0.0.1:{self.server.server_port}/?type=key&u={urllib.parse.quote(a)}&r={urllib.parse.quote(ref)}"
                                    out.append(t[:um.start(1)] + nu + t[um.end(1):])
                                else: out.append(line)
                            else: out.append(line)
                        data = "\n".join(out).encode("utf-8")
                        ctype = "application/vnd.apple.mpegurl"
                    elif typ == "seg":
                        ctype = "video/mp2t"
                    self.send_response(200)
                    self.send_header("Content-Type", ctype)
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                except Exception:
                    self.send_response(404); self.end_headers()
        self.server = http.server.HTTPServer(("127.0.0.1", 0), H)
        self.port = self.server.server_port
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def url(self, typ, u, ref=""):
        return f"http://127.0.0.1:{self.port}/?type={typ}&u={urllib.parse.quote(u)}&r={urllib.parse.quote(ref or BASE+'/')}"

_RELAY = _Relay()

class Spider:
    def init(self, extend=""):
        self.extend = extend or ""

    def homeContent(self, filter=False):
        html = _http(BASE + "/")
        return json.dumps({"class": [{"type_id": i, "type_name": n} for n, i in CLASSES], "list": _cards(html)}, ensure_ascii=False)

    def homeVideoContent(self):
        return json.dumps({"list": _cards(_http(BASE + "/"))}, ensure_ascii=False)

    def categoryContent(self, tid, pg, filter=False, extend=None):
        page = max(1, int(pg or 1))
        url = f"{BASE}/video/{tid}" + (f"?page={page}" if page > 1 else "")
        lst = _cards(_http(url))
        return json.dumps({"page": page, "pagecount": page + 1 if len(lst) >= PAGE_SIZE else page,
                           "limit": len(lst), "total": 999999 if len(lst) >= PAGE_SIZE else len(lst),
                           "list": lst}, ensure_ascii=False)

    def detailContent(self, ids):
        vid = ids[0] if ids else ""
        if not vid: return json.dumps({"list": []}, ensure_ascii=False)
        html = _http(f"{BASE}/video/{vid}.html")
        name = _ent(_first(html, r'<h1[^>]*itemprop="name"[^>]*>([^<]+)</h1>')) or _ent(_first(html, r'<title>([^<]+) - ')) or "成人俱乐部"
        pic = _first(html, r'(?:data-cover-src|data-src|src)="([^"]+\.(?:jpg|jpeg|png|webp)(?:\?[^"]*)?)"')
        if pic and pic.startswith("//"): pic = "https:" + pic
        elif pic and pic.startswith("/"): pic = BASE + pic
        desc = _ent(_first(html, r'itemprop="description"[^>]*>([^<]+)<'))
        playUrl = _first(html, r'href="(/play/[a-z0-9-]+\.html)"')
        if playUrl and playUrl.startswith("/"): playUrl = BASE + playUrl
        if not playUrl: playUrl = f"{BASE}/play/{vid}.html"
        vod = {"vod_id": vid, "vod_name": name, "vod_pic": _RELAY.url("img", pic) if pic else "",
               "vod_remarks": "在线",
               "vod_content": f"【站源】成人俱乐部（18hub）· 自研模板\n【取流】播放页 data-player-token base64编码m3u8，master playlist→子清单→明文TS\n【搜索】GET /video/search=关键词（需URL编码）\n" + (f"【简介】{desc}" if desc else ""),
               "vod_play_from": "18hub", "vod_play_url": f"在线播放${playUrl}"}
        return json.dumps({"list": [vod]}, ensure_ascii=False)

    def playerContent(self, flag, id, vipFlags=None):
        src = id or ""
        if ".m3u8" not in src:
            html = _http(src)
            token = _first(html, r'data-player-token="([^"]+)"') or _first(html, r'data-video-token="([^"]+)"')
            if token:
                try:
                    m3u8 = base64.b64decode(token).decode("utf-8").strip()
                    if "http" in m3u8: src = m3u8
                except Exception: pass
            if ".m3u8" not in src:
                m = re.search(r'(https?://[^"\'\s]+\.m3u8)', html)
                if m: src = m.group(1)
        if not src or ".m3u8" not in src:
            return json.dumps({"parse": 0, "url": src, "header": json.dumps({"User-Agent": UA})}, ensure_ascii=False)
        pu = _RELAY.url("hls", src, BASE + "/")
        return json.dumps({"parse": 0, "url": pu, "header": json.dumps({"User-Agent": UA})}, ensure_ascii=False)

    def searchContent(self, key, quick=False, pg="1"):
        if not key: return json.dumps({"list": []}, ensure_ascii=False)
        page = max(1, int(pg or 1))
        url = f"{BASE}/video/search={urllib.parse.quote(key)}" + (f"?page={page}" if page > 1 else "")
        lst = _cards(_http(url))
        return json.dumps({"page": page, "pagecount": page + 1 if len(lst) >= PAGE_SIZE else page,
                           "limit": len(lst), "total": len(lst), "list": lst}, ensure_ascii=False)

if __name__ == "__main__":
    s = Spider()
    s.init("")
    ok = fail = 0
    def check(name, cond, extra=""):
        global ok, fail
        if cond: ok += 1; print(f"  PASS {name}")
        else: fail += 1; print(f"  FAIL {name} {extra}")

    print("=== 成人俱乐部（18hub）Python 插件自检 ===")
    h = json.loads(s.homeContent())
    check("首页分类数=19", len(h["class"]) == 19, f"实际{len(h['class'])}")
    check("首页视频>0", len(h["list"]) > 0, f"实际{len(h['list'])}")
    if h["list"]:
        v = h["list"][0]
        check("首页首条id非空", bool(v["vod_id"]))
        check("首页首条name非空", bool(v["vod_name"]), v["vod_name"][:20])

    c = json.loads(s.categoryContent("zhuboa", "1"))
    check("分类zhuboa视频>0", len(c["list"]) > 0, f"实际{len(c['list'])}")
    c2 = json.loads(s.categoryContent("zhuboa", "2"))
    check("翻页换内容", c["list"] and c2["list"] and c["list"][0]["vod_id"] != c2["list"][0]["vod_id"])

    if c["list"]:
        vid = c["list"][0]["vod_id"]
        d = json.loads(s.detailContent([vid]))
        check("详情返回1条", len(d["list"]) == 1)
        if d["list"]:
            dv = d["list"][0]
            check("详情标题非空", bool(dv["vod_name"]), dv["vod_name"][:20])
            check("详情播放地址非空", bool(dv["vod_play_url"]))
            if dv["vod_play_url"]:
                ep = dv["vod_play_url"].split("#")[0].split("$", 1)
                if len(ep) == 2:
                    check("播放地址是播放页", "/play/" in ep[1], ep[1][:60])
                    p = json.loads(s.playerContent("", ep[1]))
                    check("播放返回url", "url" in p and bool(p["url"]))

    sr = json.loads(s.searchContent("学生"))
    check("搜索有结果", len(sr["list"]) > 0, f"实际{len(sr['list'])}")
    sr2 = json.loads(s.searchContent("不存在的词xyz123"))
    check("空搜索不崩", isinstance(sr2, dict))

    print(f"\n=== PASS={ok} FAIL={fail} ===")
    sys.exit(0 if fail == 0 else 1)

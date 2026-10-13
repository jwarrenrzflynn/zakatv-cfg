#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""YY淫院（yy37）TVBox Python 插件 · 纯标准库 · 全页base64编码"""
import json, re, sys, base64, urllib.request, urllib.parse, http.server, threading

BASE = "https://auzcexktg.yinmi37.vip"
UA = "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 Chrome/131.0.0.0 Mobile Safari/537.36"
PAGE_SIZE = 24

CLASSES = [
    ("中文字幕", "51"), ("国产视频", "52"), ("国产传媒", "53"), ("日本有码", "54"),
    ("日本无码", "55"), ("欧美无码", "56"), ("激情动漫", "57"), ("明星换脸", "58"),
    ("抖阴视频", "59"), ("女优明星", "60"), ("网红头条", "61"), ("AV解说", "62"),
    ("SM调教", "63"), ("极品媚黑", "64"), ("人妖系列", "65"), ("美女主播", "66"),
    ("伦理三级", "68"), ("其他类型", "69"),
]

def _decode_if_needed(html):
    """全站页面被 atob(base64) → JSON字节数组 → UTF-8 编码"""
    if not html or "atob(" not in html:
        return html
    m = re.search(r'atob\("([^"]+)"\)', html)
    if not m:
        return html
    try:
        raw = base64.b64decode(m.group(1))
        arr = json.loads(raw)
        decoded = bytes(arr).decode("utf-8", errors="ignore")
        return decoded if len(decoded) > 100 else html
    except Exception:
        return html

def _http(url, ref=""):
    headers = {"User-Agent": UA, "Referer": ref or BASE + "/",
               "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
               "Accept-Language": "zh-CN,zh;q=0.9"}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return _decode_if_needed(r.read().decode("utf-8", errors="ignore"))
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
    for m in re.finditer(r'<a[^>]*href="(/voddetail/(\d+)\.html)"[^>]*>(.*?)</a>', html, re.S):
        href, vid, body = m.group(1), m.group(2), m.group(3)
        if vid in seen: continue
        seen.add(vid)
        name = _ent(_first(body, r'<img[^>]*alt="([^"]+)"')) or _ent(_first(body, r'<strong[^>]*>([^<]+)</strong>'))
        if not name:
            name = _ent(re.sub(r"<[^>]+>", "", body).strip()) or vid
        pic = _first(body, r'(?:data-src|data-original|src)="([^"]+\.(?:jpg|jpeg|png|webp)(?:\?[^"]*)?)"')
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
        url = f"{BASE}/vodtype/{tid}" + (f"-{page}" if page > 1 else "") + ".html"
        lst = _cards(_http(url))
        return json.dumps({"page": page, "pagecount": page + 1 if len(lst) >= PAGE_SIZE else page,
                           "limit": len(lst), "total": 999999 if len(lst) >= PAGE_SIZE else len(lst),
                           "list": lst}, ensure_ascii=False)

    def detailContent(self, ids):
        vid = ids[0] if ids else ""
        if not vid: return json.dumps({"list": []}, ensure_ascii=False)
        html = _http(f"{BASE}/voddetail/{vid}.html")
        name = _ent(_first(html, r"<h2[^>]*>([^<]+)</h2>")) or _ent(_first(html, r"<title>([^<]+) - ")) or "YY淫院"
        pic = _first(html, r'(?:data-src|src)="([^"]+\.(?:jpg|jpeg|png|webp)(?:\?[^"]*)?)"')
        if pic and pic.startswith("//"): pic = "https:" + pic
        elif pic and pic.startswith("/"): pic = BASE + pic
        desc = _ent(_first(html, r'name="description" content="([^"]+)"'))
        playUrl = f"{BASE}/vodplay/{vid}-1-1.html"
        vod = {"vod_id": vid, "vod_name": name, "vod_pic": _RELAY.url("img", pic) if pic else "",
               "vod_remarks": "在线",
               "vod_content": f"【站源】YY淫院·自研模板（全页base64编码）\n【取流】播放页data-user-name明文m3u8，master playlist→子清单→明文TS\n【搜索】GET /vod/search.html?wd=\n" + (f"【简介】{desc}" if desc else ""),
               "vod_play_from": "YY淫院", "vod_play_url": f"在线播放${playUrl}"}
        return json.dumps({"list": [vod]}, ensure_ascii=False)

    def playerContent(self, flag, id, vipFlags=None):
        src = id or ""
        if ".m3u8" not in src:
            html = _http(src)
            dun = _first(html, r'data-user-name="([^"]+)"')
            if dun and "$" in dun:
                parts = dun.split("$", 1)
                if len(parts) == 2 and "http" in parts[1]:
                    src = parts[1].strip()
            else:
                m = re.search(r'(https?://[^"\'\s]+\.m3u8)', html)
                if m: src = m.group(1)
        if not src or ".m3u8" not in src:
            return json.dumps({"parse": 0, "url": src, "header": json.dumps({"User-Agent": UA})}, ensure_ascii=False)
        pu = _RELAY.url("hls", src, BASE + "/")
        return json.dumps({"parse": 0, "url": pu, "header": json.dumps({"User-Agent": UA})}, ensure_ascii=False)

    def searchContent(self, key, quick=False, pg="1"):
        if not key: return json.dumps({"list": []}, ensure_ascii=False)
        page = max(1, int(pg or 1))
        url = f"{BASE}/vod/search.html?wd={urllib.parse.quote(key)}" + (f"&page={page}" if page > 1 else "")
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

    print("=== YY淫院 Python 插件自检 ===")
    h = json.loads(s.homeContent())
    check("首页分类数=18", len(h["class"]) == 18, f"实际{len(h['class'])}")
    check("首页视频>0", len(h["list"]) > 0, f"实际{len(h['list'])}")
    if h["list"]:
        v = h["list"][0]
        check("首页首条id非空", bool(v["vod_id"]))
        check("首页首条name非空", bool(v["vod_name"]), v["vod_name"][:20])

    c = json.loads(s.categoryContent("51", "1"))
    check("分类51视频>0", len(c["list"]) > 0, f"实际{len(c['list'])}")
    c2 = json.loads(s.categoryContent("51", "2"))
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
                    check("播放地址是播放页", "/vodplay/" in ep[1], ep[1][:60])
                    p = json.loads(s.playerContent("", ep[1]))
                    check("播放返回url", "url" in p and bool(p["url"]))

    sr = json.loads(s.searchContent("学生"))
    check("搜索有结果", len(sr["list"]) > 0, f"实际{len(sr['list'])}")
    sr2 = json.loads(s.searchContent("不存在的词xyz123"))
    check("空搜索不崩", isinstance(sr2, dict))

    print(f"\n=== PASS={ok} FAIL={fail} ===")
    sys.exit(0 if fail == 0 else 1)

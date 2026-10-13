#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""超短剧（shanekids）TVBox Python 插件 · 纯标准库 · AI色情短剧站"""
import json, re, sys, urllib.request, urllib.parse, http.server, threading

BASE = "https://www.shanekids.com"
UA = "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 Chrome/131.0.0.0 Mobile Safari/537.36"
PAGE_SIZE = 30

CLASSES = [
    ("全部", "explore"), ("都市", "都市"), ("高颜值", "高颜值"), ("现代", "现代"),
    ("剧情", "剧情"), ("熟女", "熟女"), ("大男主", "大男主"), ("后宫", "后宫"),
    ("大女主", "大女主"), ("奇幻", "奇幻"), ("乱伦", "乱伦"), ("古风", "古风"),
    ("校园", "校园"), ("绿帽", "绿帽"), ("逆袭", "逆袭"), ("职场", "职场"),
    ("甜宠", "甜宠"), ("穿越", "穿越"), ("系统", "系统"), ("同性", "同性"),
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
    for m in re.finditer(r'<a[^>]*class="[^"]*card[^"]*"[^>]*href="/drama/([a-zA-Z0-9]+)"[^>]*title="([^"]*)"[^>]*>(.*?)</a>', html, re.S):
        vid, name, body = m.group(1), _ent(m.group(2)), m.group(3)
        if vid in seen: continue
        seen.add(vid)
        pic = _first(body, r'(?:data-src|data-original|src)="([^"]+\.(?:webp|jpg|jpeg|png)(?:\?[^"]*)?)"')
        if pic and pic.startswith("//"): pic = "https:" + pic
        elif pic and pic.startswith("/"): pic = BASE + pic
        eps = _first(body, r'class="card-eps"[^>]*>([^<]+)<')
        out.append({"vod_id": vid, "vod_name": name or vid, "vod_pic": pic,
                    "vod_remarks": eps or "在线"})
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
        if tid == "explore":
            url = f"{BASE}/explore?sort=hot" + (f"&page={page}" if page > 1 else "")
        else:
            url = f"{BASE}/tag/{urllib.parse.quote(tid)}" + (f"?page={page}" if page > 1 else "")
        lst = _cards(_http(url))
        return json.dumps({"page": page, "pagecount": page + 1 if len(lst) >= PAGE_SIZE else page,
                           "limit": len(lst), "total": 999999 if len(lst) >= PAGE_SIZE else len(lst),
                           "list": lst}, ensure_ascii=False)

    def detailContent(self, ids):
        vid = ids[0] if ids else ""
        if not vid: return json.dumps({"list": []}, ensure_ascii=False)
        html = _http(f"{BASE}/drama/{vid}")
        name = _ent(_first(html, r'<h1[^>]*class="[^"]*watch-title[^"]*"[^>]*>([^<]+)</h1>')) or _ent(_first(html, r"<title>([^<]+) - ")) or "超短剧"
        pic = _first(html, r'poster="([^"]+)"') or _first(html, r'(?:data-src|data-original|src)="([^"]+\.(?:webp|jpg|jpeg|png)(?:\?[^"]*)?)"')
        if pic and pic.startswith("//"): pic = "https:" + pic
        elif pic and pic.startswith("/"): pic = BASE + pic
        desc = _ent(_first(html, r'<p[^>]*class="[^"]*watch-desc[^"]*"[^>]*>(.*?)</p>'))
        eps = _first(html, r"<span>(\d+\s*集)</span>")

        play_url = ""
        pd = _first(html, r'<script[^>]*id="player-data"[^>]*type="application/json"[^>]*>(.*?)</script>')
        if pd:
            try:
                arr = json.loads(pd)
                parts = []
                for ep in arr:
                    seq = str(ep.get("seq", ""))
                    src = ep.get("src", "")
                    if src: parts.append(f"第{seq}集${src}")
                play_url = "#".join(parts)
            except Exception: pass
        if not play_url:
            parts = []
            for m in re.finditer(r'class="ep-btn"[^>]*data-src="([^"]+)"[^>]*data-seq="(\d+)"', html, re.I):
                parts.append(f"第{m.group(2)}集${m.group(1)}")
            play_url = "#".join(parts)

        vod = {"vod_id": vid, "vod_name": name, "vod_pic": _RELAY.url("img", pic) if pic else "",
               "vod_remarks": eps or "在线",
               "vod_content": f"【站源】超短剧 · AI色情短剧站（自研模板·Cloudflare）\n【取流】详情页 player-data JSON 直接含全部剧集 m3u8\n【加密】m3u8 AES-128（crypt.key 相对路径），本机代理处理\n【出流】stream.megafile.media\n【搜索】/search?q={{URL编码}}\n" + (f"【简介】{desc}" if desc else ""),
               "vod_play_from": "超短剧", "vod_play_url": play_url}
        return json.dumps({"list": [vod]}, ensure_ascii=False)

    def playerContent(self, flag, id, vipFlags=None):
        src = id or ""
        if not src or ".m3u8" not in src:
            return json.dumps({"parse": 0, "url": src, "header": json.dumps({"User-Agent": UA})}, ensure_ascii=False)
        pu = _RELAY.url("hls", src, BASE + "/")
        return json.dumps({"parse": 0, "url": pu, "header": json.dumps({"User-Agent": UA})}, ensure_ascii=False)

    def searchContent(self, key, quick=False, pg="1"):
        if not key: return json.dumps({"list": []}, ensure_ascii=False)
        page = max(1, int(pg or 1))
        url = f"{BASE}/search?q={urllib.parse.quote(key)}" + (f"&page={page}" if page > 1 else "")
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

    print("=== 超短剧（shanekids）Python 插件自检 ===")
    h = json.loads(s.homeContent())
    check("首页分类数=20", len(h["class"]) == 20, f"实际{len(h['class'])}")
    check("首页视频>0", len(h["list"]) > 0, f"实际{len(h['list'])}")
    if h["list"]:
        v = h["list"][0]
        check("首页首条id非空", bool(v["vod_id"]))
        check("首页首条name非空", bool(v["vod_name"]), v["vod_name"][:20])

    c = json.loads(s.categoryContent("explore", "1"))
    check("全部分类视频>0", len(c["list"]) > 0, f"实际{len(c['list'])}")
    c2 = json.loads(s.categoryContent("explore", "2"))
    check("翻页换内容", c["list"] and c2["list"] and c["list"][0]["vod_id"] != c2["list"][0]["vod_id"])

    ct = json.loads(s.categoryContent("都市", "1"))
    check("标签分类视频>0", len(ct["list"]) > 0, f"实际{len(ct['list'])}")

    if c["list"]:
        vid = c["list"][0]["vod_id"]
        d = json.loads(s.detailContent([vid]))
        check("详情返回1条", len(d["list"]) == 1)
        if d["list"]:
            dv = d["list"][0]
            check("详情标题非空", bool(dv["vod_name"]), dv["vod_name"][:20])
            check("详情播放地址非空", bool(dv["vod_play_url"]))
            check("详情剧集>1", dv["vod_play_url"].count("#") >= 1, f"集数={dv['vod_play_url'].count('#')+1}")
            if dv["vod_play_url"]:
                ep = dv["vod_play_url"].split("#")[0].split("$", 1)
                if len(ep) == 2:
                    check("播放地址是m3u8", ".m3u8" in ep[1], ep[1][:60])
                    p = json.loads(s.playerContent("", ep[1]))
                    check("播放返回url", "url" in p and bool(p["url"]))

    sr = json.loads(s.searchContent("重生"))
    check("搜索有结果", len(sr["list"]) > 0, f"实际{len(sr['list'])}")
    sr2 = json.loads(s.searchContent("不存在的词xyz123"))
    check("空搜索不崩", isinstance(sr2, dict))

    print(f"\n=== PASS={ok} FAIL={fail} ===")
    sys.exit(0 if fail == 0 else 1)

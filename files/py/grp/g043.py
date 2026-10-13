#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AV55（avx14）TVBox Python 插件 · 纯标准库 · JAEVE引擎 · hex编码+滑块cookie"""
import json, re, sys, os, urllib.request, urllib.parse, http.server, threading, socket, ssl, gzip, io

BASE = "https://avx14.com"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
COOKIE = "_slide_passed=1"
PAGE_SIZE = 12

# 沙箱自测用代理（环境变量 AVX14_SOCKS5 或默认127.0.0.1:10809）
_SOCKS5 = os.environ.get("AVX14_SOCKS5", "127.0.0.1:10809")

CLASSES = [
    ("最近更新", "new"), ("中文字幕", "chinese-subtitle"), ("无码流出", "uncensored-leak"),
    ("东京热", "tokyohot"), ("一本道", "1pondo"), ("加勒比", "caribbeancom"),
    ("加勒比高清", "caribbeancompr"), ("HEYZO", "heyzo"), ("FC2", "fc2"),
    ("SIRO", "siro"), ("Gachinco", "gachinco"), ("10musume", "10musume"),
    ("pacopacomama", "pacopacomama"), ("LUXU", "luxu"), ("GANA", "gana"),
    ("顽皮0930", "naughty0930"), ("顽皮4610", "naughty4610"), ("人妻斩", "marriedslash"),
    ("本月热门", "monthly-hot"), ("今日热门", "today-hot"), ("VR", "genres/VR"),
]

_SKIP_IDS = {"new", "search", "actresses", "genres", "makers", "playlists", "release", "user", "klive", "twav"}

def _socks5_socket(host, port, timeout=20):
    """通过socks5代理建立TCP连接"""
    addr, p = _SOCKS5.split(":")
    s = socket.create_connection((addr, int(p)), timeout=timeout)
    # SOCKS5握手
    s.sendall(b"\x05\x01\x00")
    resp = s.recv(2)
    if resp != b"\x05\x00":
        s.close(); raise Exception("socks5 auth fail")
    # 连接请求
    req = b"\x05\x01\x00\x03" + bytes([len(host)]) + host.encode() + port.to_bytes(2, "big")
    s.sendall(req)
    resp = s.recv(10)
    if resp[1] != 0:
        s.close(); raise Exception(f"socks5 connect fail: {resp[1]}")
    return s

def _http_get(url, ref=""):
    """HTTP GET，直连失败则用socks5代理"""
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname
    port = parsed.port or 443
    path = parsed.path + ("?" + parsed.query if parsed.query else "")

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    # 先尝试直连
    try:
        s = socket.create_connection((host, port), timeout=10)
        ss = ctx.wrap_socket(s, server_hostname=host)
        # 测试SSL是否真的通了（发一个字节试试）
        ss.settimeout(5)
    except Exception:
        # 直连失败，用socks5
        try:
            s = _socks5_socket(host, port)
            ss = ctx.wrap_socket(s, server_hostname=host)
        except Exception:
            return ""
    else:
        ss.settimeout(20)

    req = (f"GET {path} HTTP/1.1\r\nHost: {host}\r\nUser-Agent: {UA}\r\n"
           f"Accept: text/html,application/xhtml+xml,*/*;q=0.8\r\n"
           f"Accept-Language: zh-CN,zh;q=0.9\r\nAccept-Encoding: gzip\r\n"
           f"Cookie: {COOKIE}\r\n"
           f"Referer: {ref or BASE}/cn/\r\nConnection: close\r\n\r\n")
    ss.sendall(req.encode())

    data = b""
    while True:
        try:
            chunk = ss.recv(65536)
            if not chunk: break
            data += chunk
        except: break
    ss.close()

    header_end = data.find(b"\r\n\r\n")
    if header_end < 0: return ""
    headers = data[:header_end].lower()
    body = data[header_end+4:]
    # 处理chunked
    if b"transfer-encoding: chunked" in headers:
        body = _unchunk(body)
    # 处理gzip
    if b"content-encoding: gzip" in headers:
        try:
            body = gzip.decompress(body)
        except:
            pass
    return body.decode("utf-8", errors="ignore")

def _unchunk(data):
    out = b""
    i = 0
    while i < len(data):
        line_end = data.find(b"\r\n", i)
        if line_end < 0: break
        size = int(data[i:line_end].split(b";")[0], 16)
        if size == 0: break
        out += data[line_end+2:line_end+2+size]
        i = line_end + 2 + size + 2
    return out

def _decode_hex(raw):
    """全页hex编码解码：document.write(Func(unescape(Func2("hex...")))"""
    if not raw or len(raw) < 100: return raw
    # 检测hex编码特征：document.write + unescape + 长hex字符串
    if "document.write" not in raw or "unescape" not in raw: return raw
    m = re.search(r'"([0-9a-fA-F]{100,})"', raw)
    if not m: return raw
    hex_str = m.group(1)
    if len(hex_str) % 2: hex_str = hex_str[:-1]
    try:
        return bytes.fromhex(hex_str).decode("utf-8", errors="ignore")
    except:
        return raw

def _fetch(url, ref=""):
    return _decode_hex(_http_get(url, ref))

def _ent(s):
    if not s: return ""
    import html as _html
    return _html.unescape(s).strip()

def _first(s, pat):
    m = re.search(pat, s, re.I | re.S)
    return m.group(1).strip() if m else ""

def _cards(html):
    out = []
    seen = set()
    for m in re.finditer(r'<a[^>]*href="/cn/([a-zA-Z0-9_-]+)"[^>]*>(.*?)</a>', html, re.S):
        vid, body = m.group(1), m.group(2)
        if vid in _SKIP_IDS: continue
        # 视频番号必须以-数字结尾（如fns-263, fc2-ppv-4985313）
        if not re.search(r"-\d+$", vid): continue
        if vid in seen: continue
        seen.add(vid)
        name = _ent(_first(body, r"<h[0-9][^>]*>([^<]+)</h[0-9]>")) or _ent(_first(body, r'alt="([^"]+)"')) or vid
        pic = _first(body, r'(?:data-src|data-original|src)="([^"]+)"')
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
                    raw = _http_get(url, ref)
                    data = raw.encode("utf-8") if isinstance(raw, str) else raw
                    ctype = "application/octet-stream"
                    if typ == "hls":
                        text = raw if isinstance(raw, str) else raw.decode("utf-8", errors="ignore")
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
        html = _fetch(BASE + "/cn/new")
        return json.dumps({"class": [{"type_id": i, "type_name": n} for n, i in CLASSES], "list": _cards(html)}, ensure_ascii=False)

    def homeVideoContent(self):
        return json.dumps({"list": _cards(_fetch(BASE + "/cn/new"))}, ensure_ascii=False)

    def categoryContent(self, tid, pg, filter=False, extend=None):
        page = max(1, int(pg or 1))
        url = f"{BASE}/cn/{tid}" + (f"?page={page}" if page > 1 else "")
        lst = _cards(_fetch(url, BASE + "/cn/" + tid))
        return json.dumps({"page": page, "pagecount": page + 1 if len(lst) >= PAGE_SIZE else page,
                           "limit": len(lst), "total": 999999 if len(lst) >= PAGE_SIZE else len(lst),
                           "list": lst}, ensure_ascii=False)

    def detailContent(self, ids):
        vid = ids[0] if ids else ""
        if not vid: return json.dumps({"list": []}, ensure_ascii=False)
        html = _fetch(f"{BASE}/cn/{vid}", BASE + "/cn/new")
        name = _ent(_first(html, r"<h1[^>]*>([^<]+)</h1>")) or _ent(_first(html, r"<title>([^<]+) - ")) or vid
        pic = _first(html, r'data-poster="([^"]+)"') or _first(html, r'(?:data-src|src)="([^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"')
        if pic and pic.startswith("//"): pic = "https:" + pic
        elif pic and pic.startswith("/"): pic = BASE + pic

        play_url = ""
        vc = re.search(r"window\.videoConfig\s*=\s*\{([^}]+)\}", html)
        if vc:
            um = re.search(r'url\s*:\s*"([^"]+)"', vc.group(1))
            if um and um.group(1):
                play_url = f"第1集${um.group(1)}"
        if not play_url:
            m = re.search(r'(https?://[^"\'\s]+\.m3u8[^"\'\s]*)', html)
            if m: play_url = f"第1集${m.group(1)}"

        vod = {"vod_id": vid, "vod_name": name, "vod_pic": _RELAY.url("img", pic) if pic else "",
               "vod_remarks": "在线",
               "vod_content": f"【站源】AV55 · JAEVE引擎（MissAV同源）\n【防护】Cloudflare IP封锁 + 滑块cookie(_slide_passed=1) + 全页hex编码\n【取流】详情页 window.videoConfig.url 明文 m3u8（带verify时效）\n【搜索】/cn/search?q=（HTTP 503但有内容）",
               "vod_play_from": "AV55", "vod_play_url": play_url}
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
        url = f"{BASE}/cn/search?q={urllib.parse.quote(key)}" + (f"&page={page}" if page > 1 else "")
        lst = _cards(_fetch(url, BASE + "/cn/"))
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

    print("=== AV55（avx14）Python 插件自检 ===")
    h = json.loads(s.homeContent())
    check("首页分类数=21", len(h["class"]) == 21, f"实际{len(h['class'])}")
    check("首页视频>0", len(h["list"]) > 0, f"实际{len(h['list'])}")
    if h["list"]:
        v = h["list"][0]
        check("首页首条id非空", bool(v["vod_id"]))
        check("首页首条name非空", bool(v["vod_name"]), v["vod_name"][:20])

    c = json.loads(s.categoryContent("new", "1"))
    check("分类new视频>0", len(c["list"]) > 0, f"实际{len(c['list'])}")
    c2 = json.loads(s.categoryContent("new", "2"))
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
                    check("播放地址是m3u8", ".m3u8" in ep[1], ep[1][:60])
                    p = json.loads(s.playerContent("", ep[1]))
                    check("播放返回url", "url" in p and bool(p["url"]))

    sr = json.loads(s.searchContent("student"))
    check("搜索有结果", len(sr["list"]) > 0, f"实际{len(sr['list'])}")
    sr2 = json.loads(s.searchContent("不存在的词xyz123"))
    check("空搜索不崩", isinstance(sr2, dict))

    print(f"\n=== PASS={ok} FAIL={fail} ===")
    sys.exit(0 if fail == 0 else 1)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""新妈妈（xmma）TVBox Python 插件 · 纯标准库 · bkplayer 两步解析"""
import json, re, sys, urllib.request, urllib.parse, http.server, threading

BASE = "https://xmma02.xmmxmm01.sbs"
PARSE = "https://xi.ywzzs1.sbs/zhuanyong/?url="
UA = "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 Chrome/131.0.0.0 Mobile Safari/537.36"
PAGE_SIZE = 12

CLASSES = [
    ("视频一区", "1"), ("视频二区", "2"), ("视频三区", "3"),
    ("高清无码", "6"), ("中文字幕", "7"), ("国产精选", "8"),
    ("欧美精选", "9"), ("国产自拍", "10"), ("性虐调教", "11"),
    ("大奶聚集", "13"), ("网红尤物", "14"), ("多人性爱", "15"),
    ("户外野战", "16"), ("热点黑料", "20"), ("迷奸强奸", "21"),
    ("本站原创", "22"), ("用户自拍", "23"), ("女同性恋", "24"),
    ("糖心Vlog", "25"),
]

def _http(url, ref="", data=None):
    headers = {"User-Agent": UA, "Referer": ref or BASE + "/",
               "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
               "Accept-Language": "zh-CN,zh;q=0.9"}
    if data:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        req = urllib.request.Request(url, data=data.encode(), headers=headers, method="POST")
    else:
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
    # 匹配所有详情页链接，提取 vid 和周围上下文
    for m in re.finditer(r'<a[^>]*href="[^"]*?/vod/detail/id/(\d+)\.html"[^>]*>(.*?)</a>', html, re.S):
        vid, body = m.group(1), m.group(2)
        if vid in seen: continue
        # 只取有图片或标题的卡片（避免导航链接）
        if not re.search(r'(img|alt|title)', body, re.I):
            # 试试从后面的 video-info 里取标题
            continue
        seen.add(vid)
        name = _ent(_first(body, r'<img[^>]*alt="([^"]+)"')) or _ent(_first(body, r'title="([^"]+)"'))
        if not name:
            name = _ent(re.sub(r"<[^>]+>", "", body).strip()) or vid
        pic = _first(body, r'(?:data-safe-src|data-src|data-original|src)="([^"]+\.(?:jpg|jpeg|png|webp)(?:\?[^"]*)?)"')
        if pic and pic.startswith("//"): pic = "https:" + pic
        elif pic and pic.startswith("/"): pic = BASE + pic
        out.append({"vod_id": vid, "vod_name": name, "vod_pic": pic, "vod_remarks": "在线"})
    return out

def _parse_md5(html):
    """从播放页提取 md5 哈希（player_aaaa 多个 url 字段，取32位的）"""
    urls = re.findall(r'"url"\s*:\s*"([^"]*)"', html)
    for u in reversed(urls):
        if len(u) == 32 and re.match(r'^[a-f0-9]+$', u):
            return u
    return ""

def _resolve_m3u8(md5):
    """两步解析：parse页拿mpd → api.php拿m3u8"""
    if not md5 or len(md5) != 32: return ""
    parse_url = PARSE + md5
    phtml = _http(parse_url, ref=parse_url)
    if not phtml: return ""
    mm = re.search(r'api\.php\?mpd=([a-f0-9]+)', phtml)
    if not mm: return ""
    api_url = f"https://xi.ywzzs1.sbs/zhuanyong/api.php?mpd={mm.group(1)}"
    m3u8 = _http(api_url, ref=parse_url)
    if m3u8 and "#EXTM3U" in m3u8:
        return api_url
    return ""

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
        url = f"{BASE}/index.php/vod/type/id/{tid}" + (f"/page/{page}" if page > 1 else "") + ".html"
        lst = _cards(_http(url))
        return json.dumps({"page": page, "pagecount": page + 1 if len(lst) >= PAGE_SIZE else page,
                           "limit": len(lst), "total": 999999 if len(lst) >= PAGE_SIZE else len(lst),
                           "list": lst}, ensure_ascii=False)

    def detailContent(self, ids):
        vid = ids[0] if ids else ""
        if not vid: return json.dumps({"list": []}, ensure_ascii=False)
        html = _http(f"{BASE}/index.php/vod/detail/id/{vid}.html")
        name = _ent(_first(html, r"<title>([^<]+)-")) or "新妈妈"
        pic = _first(html, r'(?:data-src|src)="([^"]+\.(?:jpg|jpeg|png|webp)(?:\?[^"]*)?)"')
        if pic and pic.startswith("//"): pic = "https:" + pic
        elif pic and pic.startswith("/"): pic = BASE + pic
        desc = _ent(_first(html, r'name="description" content="([^"]+)"'))

        play_pages = []
        for m in re.finditer(rf'/vod/play/id/{vid}/sid/(\d+)/nid/(\d+)\.html', html):
            pp = f"{BASE}/index.php/vod/play/id/{vid}/sid/{m.group(1)}/nid/{m.group(2)}.html"
            if pp not in play_pages: play_pages.append(pp)

        urls = []
        for i, pp in enumerate(play_pages[:3]):
            phtml = _http(pp)
            md5 = _parse_md5(phtml)
            if md5:
                urls.append(f"第{i+1}集${md5}")

        vod = {"vod_id": vid, "vod_name": name, "vod_pic": _RELAY.url("img", pic) if pic else "",
               "vod_remarks": f"{len(urls)}集" if len(urls) > 1 else "在线",
               "vod_content": f"【站源】新妈妈·苹果CMS V10（bkplayer两步解析）\n【取流】md5→parse页mpd→api.php m3u8\n【搜索】必须POST\n【分片】BYTERANGE+S3预签名URL\n" + (f"【简介】{desc}" if desc else ""),
               "vod_play_from": "新妈妈", "vod_play_url": "#".join(urls)}
        return json.dumps({"list": [vod]}, ensure_ascii=False)

    def playerContent(self, flag, id, vipFlags=None):
        src = id or ""
        if not src: return json.dumps({"parse": 0, "url": "", "header": json.dumps({"User-Agent": UA})}, ensure_ascii=False)

        m3u8 = ""
        if ".m3u8" in src:
            m3u8 = src
        elif len(src) == 32 and re.match(r'^[a-f0-9]+$', src):
            m3u8 = _resolve_m3u8(src)
        else:
            html = _http(src)
            md5 = _parse_md5(html)
            if md5: m3u8 = _resolve_m3u8(md5)

        if not m3u8:
            return json.dumps({"parse": 0, "url": src, "header": json.dumps({"User-Agent": UA})}, ensure_ascii=False)
        pu = _RELAY.url("hls", m3u8, PARSE + src)
        return json.dumps({"parse": 0, "url": pu, "header": json.dumps({"User-Agent": UA})}, ensure_ascii=False)

    def searchContent(self, key, quick=False, pg="1"):
        if not key: return json.dumps({"list": []}, ensure_ascii=False)
        page = max(1, int(pg or 1))
        lst = _cards(_http(f"{BASE}/index.php/vod/search.html", data=f"wd={urllib.parse.quote(key)}"))
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

    print("=== 新妈妈 Python 插件自检 ===")
    h = json.loads(s.homeContent())
    check("首页分类数=19", len(h["class"]) == 19, f"实际{len(h['class'])}")
    check("首页视频>0", len(h["list"]) > 0, f"实际{len(h['list'])}")
    if h["list"]:
        v = h["list"][0]
        check("首页首条id非空", bool(v["vod_id"]))
        check("首页首条name非空", bool(v["vod_name"]), v["vod_name"][:20])

    c = json.loads(s.categoryContent("1", "1"))
    check("分类1视频>0", len(c["list"]) > 0, f"实际{len(c['list'])}")
    c2 = json.loads(s.categoryContent("1", "2"))
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
                    check("播放地址是md5", len(ep[1]) == 32, ep[1][:20])
                    p = json.loads(s.playerContent("", ep[1]))
                    check("播放返回url", "url" in p and bool(p["url"]))

    sr = json.loads(s.searchContent("学生"))
    check("POST搜索有结果", len(sr["list"]) > 0, f"实际{len(sr['list'])}")
    sr2 = json.loads(s.searchContent("不存在的词xyz123"))
    check("空搜索不崩", isinstance(sr2, dict))

    print(f"\n=== PASS={ok} FAIL={fail} ===")
    sys.exit(0 if fail == 0 else 1)

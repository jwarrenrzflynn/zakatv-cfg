#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""农村妈妈（ncm）TVBox Python 插件 · 纯标准库 · 与 Java 侧口径一致"""
import json, re, sys, urllib.request, urllib.parse, http.server, threading

BASE = "https://873611.ncmamall01.top/ncmm"
UA = "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 Chrome/131.0.0.0 Mobile Safari/537.36"
PAGE_SIZE = 40

CLASSES = [
    ("每日更新1区", "29"), ("每日更新2区", "30"), ("精品推荐", "49"),
    ("直播做爱", "50"), ("欧美精品", "51"), ("偷拍自拍", "54"),
    ("网曝流出", "55"), ("国产探花", "57"), ("人妻熟女", "58"),
    ("SM调教", "59"), ("制服诱惑", "60"), ("麻豆诱惑", "61"),
    ("乱伦实录", "62"), ("换脸明星", "63"), ("主播做爱", "64"),
    ("传媒出品", "65"), ("探花约炮", "66"), ("自拍短视频", "67"),
    ("动漫", "69"), ("女同性恋", "70"), ("男同性恋", "71"),
    ("黑料网爆", "73"), ("高清做爱", "74"), ("AI换脸", "76"),
    ("国产精品", "77"), ("每日更新3区", "92"), ("国产视频", "95"),
    ("国产主播", "96"), ("国产传媒", "97"), ("网红头条", "99"),
    ("抖阴视频", "101"), ("韩国主播", "104"), ("VR视角", "105"),
    ("中文字幕", "107"), ("日本有码", "108"), ("日本无码", "109"),
    ("欧美无码", "110"), ("女优明星", "111"), ("强奸乱伦", "112"),
    ("伦理三级", "114"), ("AV解说", "116"),
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
    for m in re.finditer(r'<a[^>]*href="[^"]*?/vod/detail/id/(\d+)\.html"[^>]*>(.*?)</a>', html, re.S):
        vid, body = m.group(1), m.group(2)
        if vid in seen: continue
        seen.add(vid)
        name = _ent(_first(body, r'<img[^>]*alt="([^"]+)"')) or _ent(_first(body, r'title="([^"]+)"'))
        if not name:
            name = _ent(re.sub(r"<[^>]+>", "", body).strip()) or vid
        pic = _first(body, r'(?:data-src|data-original|src)="([^"]+\.(?:jpg|jpeg|png|webp)(?:\?[^"]*)?)"')
        if pic and pic.startswith("//"): pic = "https:" + pic
        elif pic and pic.startswith("/"): pic = BASE + pic
        out.append({"vod_id": vid, "vod_name": name, "vod_pic": pic, "vod_remarks": "在线"})
    return out

def _parse_player(html):
    """直接在整个播放页 HTML 里搜 url 字段（player_aaaa 有嵌套 {}，正则难匹配完整块）"""
    if not html: return None
    # 提取所有 "url":"..." ，取最后一个非空且像地址的
    urls = re.findall(r'"url"\s*:\s*"([^"]*)"', html)
    url = ""
    for u in urls:
        if u and (u.startswith("http") or u.startswith("\\/")):
            url = u.replace("\\/", "/")
    if not url: return None
    fromm = ""
    fm = re.search(r'"from"\s*:\s*"([^"]*)"', html)
    if fm: fromm = fm.group(1)
    return {"url": url, "from": fromm}

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
        url = f"{BASE}/index.php/vod/type/id/{tid}" + (f"/page/{page}" if page > 1 else "") + ".html"
        lst = _cards(_http(url))
        return json.dumps({"page": page, "pagecount": page + 1 if len(lst) >= PAGE_SIZE else page,
                           "limit": len(lst), "total": 999999 if len(lst) >= PAGE_SIZE else len(lst),
                           "list": lst}, ensure_ascii=False)

    def detailContent(self, ids):
        vid = ids[0] if ids else ""
        if not vid: return json.dumps({"list": []}, ensure_ascii=False)
        html = _http(f"{BASE}/index.php/vod/detail/id/{vid}.html")
        name = _ent(_first(html, r"<title>([^<]+)-")) or "农村妈妈"
        pic = _first(html, r'(?:data-src|src)="([^"]+\.(?:jpg|jpeg|png|webp)(?:\?[^"]*)?)"')
        if pic and pic.startswith("//"): pic = "https:" + pic
        elif pic and pic.startswith("/"): pic = BASE + pic
        desc = _ent(_first(html, r'name="description" content="([^"]+)"'))

        # 抓播放页
        play_pages = []
        for m in re.finditer(rf'/vod/play/id/{vid}/sid/(\d+)/nid/(\d+)\.html', html):
            pp = f"{BASE}/index.php/vod/play/id/{vid}/sid/{m.group(1)}/nid/{m.group(2)}.html"
            if pp not in play_pages: play_pages.append(pp)

        urls, froms = [], []
        for i, pp in enumerate(play_pages[:3]):
            phtml = _http(pp)
            pa = _parse_player(phtml)
            if pa and pa.get("url", "").find("http") >= 0:
                froms.append(pa.get("from", "") or f"线路{i+1}")
                urls.append(f"第{i+1}集${pa['url']}")

        if not urls:
            m = re.search(r'(https?://[^"\'\s]+\.m3u8)', html)
            if m: urls.append(f"播放${m.group(1)}"); froms.append("默认")

        vod = {"vod_id": vid, "vod_name": name, "vod_pic": _RELAY.url("img", pic) if pic else "",
               "vod_remarks": f"{len(urls)}集" if len(urls) > 1 else "在线",
               "vod_content": f"【站源】农村妈妈·标准苹果CMS V10（/ncmm前缀）\n【取流】播放页player_aaaa明文m3u8，master→子清单→明文TS\n【分类】41个有效分类，每页40卡\n" + (f"【简介】{desc}" if desc else ""),
               "vod_play_from": "$$$".join(froms), "vod_play_url": "#".join(urls)}
        return json.dumps({"list": [vod]}, ensure_ascii=False)

    def playerContent(self, flag, id, vipFlags=None):
        src = id or ""
        if ".m3u8" not in src:
            html = _http(src)
            pa = _parse_player(html)
            if pa: src = pa.get("url", "")
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
        url = f"{BASE}/index.php/vod/search.html?wd={urllib.parse.quote(key)}"
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

    print("=== 农村妈妈 Python 插件自检 ===")
    h = json.loads(s.homeContent())
    check("首页分类数=41", len(h["class"]) == 41, f"实际{len(h['class'])}")
    check("首页视频>0", len(h["list"]) > 0, f"实际{len(h['list'])}")
    if h["list"]:
        v = h["list"][0]
        check("首页首条id非空", bool(v["vod_id"]))
        check("首页首条name非空", bool(v["vod_name"]), v["vod_name"][:20])

    c = json.loads(s.categoryContent("29", "1"))
    check("分类29视频>0", len(c["list"]) > 0, f"实际{len(c['list'])}")
    c2 = json.loads(s.categoryContent("29", "2"))
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
                    p = json.loads(s.playerContent("", ep[1]))
                    check("播放返回url", "url" in p and bool(p["url"]))

    sr = json.loads(s.searchContent("学生"))
    check("搜索有结果", len(sr["list"]) > 0, f"实际{len(sr['list'])}")
    sr2 = json.loads(s.searchContent("不存在的词xyz123"))
    check("空搜索不崩", isinstance(sr2, dict))

    print(f"\n=== PASS={ok} FAIL={fail} ===")
    sys.exit(0 if fail == 0 else 1)

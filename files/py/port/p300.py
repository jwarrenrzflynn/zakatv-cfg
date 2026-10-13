# -*- coding: utf-8 -*-
import json
import base64
import re
import urllib.request
import urllib.parse
import gzip
import zlib
import ssl

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        pass

def format_remarks(brand="ZakaTV", meta=""):
    clean_meta = str(meta or "").strip()
    clean_meta = " ".join(clean_meta.split())
    if clean_meta:
        return "%s | %s" % (brand, clean_meta)
    return brand

_AES_SBOX = (
    0x63,0x7c,0x77,0x7b,0xf2,0x6b,0x6f,0xc5,0x30,0x01,0x67,0x2b,0xfe,0xd7,0xab,0x76,
    0xca,0x82,0xc9,0x7d,0xfa,0x59,0x47,0xf0,0xad,0xd4,0xa2,0xaf,0x9c,0xa4,0x72,0xc0,
    0xb7,0xfd,0x93,0x26,0x36,0x3f,0xf7,0xcc,0x34,0xa5,0xe5,0xf1,0x71,0xd8,0x31,0x15,
    0x04,0xc7,0x23,0xc3,0x18,0x96,0x05,0x9a,0x07,0x12,0x80,0xe2,0xeb,0x27,0xb2,0x75,
    0x09,0x83,0x2c,0x1a,0x1b,0x6e,0x5a,0xa0,0x52,0x3b,0xd6,0xb3,0x29,0xe3,0x2f,0x84,
    0x53,0xd1,0x00,0xed,0x20,0xfc,0xb1,0x5b,0x6a,0xcb,0xbe,0x39,0x4a,0x4c,0x58,0xcf,
    0xd0,0xef,0xaa,0xfb,0x43,0x4d,0x33,0x85,0x45,0xf9,0x02,0x7f,0x50,0x3c,0x9f,0xa8,
    0x51,0xa3,0x40,0x8f,0x92,0x9d,0x38,0xf5,0xbc,0xb6,0xda,0x21,0x10,0xff,0xf3,0xd2,
    0xcd,0x0c,0x13,0xec,0x5f,0x97,0x44,0x17,0xc4,0xa7,0x7e,0x3d,0x64,0x5d,0x19,0x73,
    0x60,0x81,0x4f,0xdc,0x22,0x2a,0x90,0x88,0x46,0xee,0xb8,0x14,0xde,0x5e,0x0b,0xdb,
    0xE0,0x32,0x3a,0x0a,0x49,0x06,0x24,0x5c,0xc2,0xd3,0xac,0x62,0x91,0x95,0xe4,0x79,
    0xe7,0xc8,0x37,0x6d,0x8d,0xd5,0x4e,0xa9,0x6c,0x56,0xf4,0xea,0x65,0x7a,0xae,0x08,
    0xba,0x78,0x25,0x2e,0x1c,0xa6,0xb4,0xc6,0xe8,0xdd,0x74,0x1f,0x4b,0xbd,0x8b,0x8a,
    0x70,0x3e,0xb5,0x66,0x48,0x03,0xf6,0x0e,0x61,0x35,0x57,0xb9,0x86,0xc1,0x1d,0x9e,
    0xe1,0xf8,0x98,0x11,0x69,0xd9,0x8e,0x94,0x9b,0x1e,0x87,0xe9,0xce,0x55,0x28,0xdf,
    0x8c,0xa1,0x89,0x0d,0xbf,0xe6,0x42,0x68,0x41,0x99,0x2d,0x0f,0xb0,0x54,0xbb,0x16
)
_AES_INV_SBOX = [0] * 256
for _i, _v in enumerate(_AES_SBOX):
    _AES_INV_SBOX[_v] = _i
_AES_INV_SBOX = tuple(_AES_INV_SBOX)
_AES_RCON = (0x01,0x02,0x04,0x08,0x10,0x20,0x40,0x80,0x1b,0x36)

def _aes_xtime(a):
    return (((a << 1) ^ 0x1b) & 0xff) if (a & 0x80) else ((a << 1) & 0xff)

def _aes_gmul(a, b):
    p = 0
    while b:
        if b & 1:
            p ^= a
        a = _aes_xtime(a)
        b >>= 1
    return p

_AES_M09 = tuple(_aes_gmul(i, 0x09) for i in range(256))
_AES_M0B = tuple(_aes_gmul(i, 0x0b) for i in range(256))
_AES_M0D = tuple(_aes_gmul(i, 0x0d) for i in range(256))
_AES_M0E = tuple(_aes_gmul(i, 0x0e) for i in range(256))

def _aes_expand_key(key):
    ek = list(key)
    for i in range(10):
        t = ek[-4:]
        t = t[1:] + t[:1]
        t = [_AES_SBOX[b] for b in t]
        t[0] ^= _AES_RCON[i]
        for _j in range(4):
            t = [t[k] ^ ek[-16+k] for k in range(4)]
            ek += t
    return [ek[i:i+16] for i in range(0, 176, 16)]

def _aes_decrypt_block(blk, rk):
    s = [a ^ b for a, b in zip(blk, rk[10])]
    for r in range(9, 0, -1):
        s = [s[0],s[13],s[10],s[7],s[4],s[1],s[14],s[11],s[8],s[5],s[2],s[15],s[12],s[9],s[6],s[3]]
        s = [_AES_INV_SBOX[b] for b in s]
        s = [a ^ b for a, b in zip(s, rk[r])]
        o = [0] * 16
        for c in range(4):
            a0, a1, a2, a3 = s[c*4], s[c*4+1], s[c*4+2], s[c*4+3]
            o[c*4]   = _AES_M0E[a0] ^ _AES_M0B[a1] ^ _AES_M0D[a2] ^ _AES_M09[a3]
            o[c*4+1] = _AES_M09[a0] ^ _AES_M0E[a1] ^ _AES_M0B[a2] ^ _AES_M0D[a3]
            o[c*4+2] = _AES_M0D[a0] ^ _AES_M09[a1] ^ _AES_M0E[a2] ^ _AES_M0B[a3]
            o[c*4+3] = _AES_M0B[a0] ^ _AES_M0D[a1] ^ _AES_M09[a2] ^ _AES_M0E[a3]
        s = o
    s = [s[0],s[13],s[10],s[7],s[4],s[1],s[14],s[11],s[8],s[5],s[2],s[15],s[12],s[9],s[6],s[3]]
    s = [_AES_INV_SBOX[b] for b in s]
    return bytes(a ^ b for a, b in zip(s, rk[0]))

class _FastAesCbc(object):
    def __init__(self, key, iv):
        self.rk = _aes_expand_key(key)
        self.iv = bytes(iv)

    def decrypt(self, data):
        out = bytearray()
        prev = self.iv
        for i in range(0, len(data) - 15, 16):
            blk = _aes_decrypt_block(data[i:i+16], self.rk)
            out += bytes(a ^ b for a, b in zip(blk, prev))
            prev = data[i:i+16]
        pad = out[-1]
        if 1 <= pad <= 16 and bytes(out[-pad:]) == bytes([pad]) * pad:
            del out[-pad:]
        return bytes(out)

_CIPHER_KEY = b"f5d965df75336270"
_CIPHER_IV = b"97b60394abc2fbe1"

def decrypt_image_payload(raw):
    if len(raw) > 2 and ((raw[0] == 0xFF and raw[1] == 0xD8) or (raw[0] == 0x89 and raw[1] == 0x50)):
        return raw
    try:
        cipher = _FastAesCbc(_CIPHER_KEY, _CIPHER_IV)
        return cipher.decrypt(raw)
    except Exception:
        return raw


class Spider(BaseSpider):
    def __init__(self):
        super(Spider, self).__init__()
        self.siteUrl = "https://pku.daqbqrri.cc"
        self.brandActor = "📺TG群: https://t.me/+3t5XRPPo9mlkZDRl"
        self.brandDirector = "📺ZakaTV"
        self.tgGroup = "https://t.me/+3t5XRPPo9mlkZDRl"
        self._ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15"

        self.ctx = ssl.create_default_context()
        self.ctx.check_hostname = False
        self.ctx.verify_mode = ssl.CERT_NONE

    def init(self, extend=""):
        return True

    def _fetch(self, url, referer=""):
        if url.startswith("//"):
            url = "https:" + url
        elif url.startswith("/"):
            url = self.siteUrl + url
        req_headers = {
            "User-Agent": self._ua,
            "Referer": referer if referer else (self.siteUrl + "/"),
            "Accept": "*/*",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive"
        }
        try:
            req = urllib.request.Request(url, headers=req_headers)
            with urllib.request.urlopen(req, timeout=12, context=self.ctx) as resp:
                code = resp.getcode()
                final_url = resp.geturl()
                raw = resp.read()
                enc = resp.headers.get("Content-Encoding", "")
                if raw.startswith(b"\x1f\x8b") or enc == "gzip":
                    raw = gzip.decompress(raw)
                elif enc == "deflate":
                    try:
                        raw = zlib.decompress(raw)
                    except Exception:
                        raw = zlib.decompress(raw, -zlib.MAX_WBITS)
                try:
                    text = raw.decode("utf-8")
                except Exception:
                    text = raw.decode("latin1", errors="ignore")
                return {"code": code, "final_url": final_url, "text": text, "bytes": raw, "bytes_len": len(raw), "err": ""}
        except urllib.error.HTTPError as e:
            return {"code": e.code, "final_url": url, "text": "", "bytes": b"", "bytes_len": 0, "err": str(e)}
        except Exception as e:
            return {"code": -1, "final_url": url, "text": "", "bytes": b"", "bytes_len": 0, "err": str(e)}

    def _build_proxy_pic(self, pic_url):
        if not pic_url:
            return ""
        if pic_url.startswith("//"):
            pic_url = "https:" + pic_url
        elif pic_url.startswith("/"):
            pic_url = self.siteUrl + pic_url
        if "wirqed.cn" not in pic_url:
            return pic_url
        b64_url = base64.urlsafe_b64encode(pic_url.encode("utf-8")).decode("ascii").rstrip("=")
        return "http://127.0.0.1:9978/proxy?do=py&type=img&u=%s" % b64_url

    def homeContent(self, filter=None):
        cats = [
            {"type_id": "/videos/guochan-sm/", "type_name": "国产SM"},
            {"type_id": "/videos/rihan-sm/", "type_name": "日韩SM"},
            {"type_id": "/videos/oumei-sm/", "type_name": "欧美SM"},
            {"type_id": "/videos/dongman-sm/", "type_name": "动漫SM"},
            {"type_id": "/videos/tiaojiao-av/", "type_name": "调教AV"},
            {"type_id": "/videos/zhibo-huifang/", "type_name": "直播回放"},
            {"type_id": "/porn/all/", "type_name": "成人视频"},
            {"type_id": "/porn/guochan-tanhua/", "type_name": "国产探花"},
            {"type_id": "/porn/rihan-av/", "type_name": "日韩AV"},
            {"type_id": "/porn/oumei-wuma/", "type_name": "欧美无码"},
            {"type_id": "/porn/heiren-zhuanqu/", "type_name": "黑人专区"},
            {"type_id": "/porn/lvmao-yinqi/", "type_name": "绿帽淫妻"},
            {"type_id": "/porn/chigua-baoliao/", "type_name": "黑料吃瓜"},
            {"type_id": "/ai/all/", "type_name": "AI短剧"},
            {"type_id": "/moviesets/", "type_name": "视频合集"}
        ]
        res = {"class": cats}
        if filter:
            res["filters"] = {}
        return res

    def homeVideoContent(self):
        return {"list": []}

    def _parse_card_list(self, html):
        scoped_html = html
        for pat in [
            r'<header[\s\S]*?</header>',
            r'<nav[\s\S]*?</nav>',
            r'<div[^>]*class=["\'][^"\']*(?:mobile-search|search-box|top-rank|ranking|sidebar)[^"\']*["\'][\s\S]*?</div>'
        ]:
            scoped_html = re.sub(pat, '', scoped_html, flags=re.I)

        main_match = re.search(r'(<main[\s\S]*?</main>)', scoped_html, re.I)
        if main_match:
            scoped_html = main_match.group(1)

        raw_items = re.findall(r'(<div[^>]*class=["\'][^"\']*(?:col-|video-item|item)[\s\S]*?</div>\s*</div>)', scoped_html, re.I)
        if not raw_items:
            raw_items = re.findall(r'(<a[^>]*href=["\'][^"\']*(?:/vd-|/videos/|/porn/|/moviesets/)[^"\']*["\'][\s\S]*?</a>)', scoped_html, re.I)

        cards = []
        seen_ids = set()

        for item in raw_items:
            href_m = re.search(r'href=["\']([^"\']*(?:/vd-|/videos/|/porn/|/moviesets/)[^"\']*)["\']', item, re.I)
            if not href_m:
                continue
            href = href_m.group(1).strip()
            
            if any(bad in href for bad in ("/hot/", "search", "login", "register", "javascript", "#", ".svg", ".png")):
                continue
            if href in seen_ids:
                continue

            title = ""
            for pat in [
                r'alt=["\']([^"\']+)["\']',
                r'title=["\']([^"\']+)["\']',
                r'class=["\'][^"\']*(?:title|name)[^"\']*["\'][^>]*>([\s\S]*?)<',
                r'<h\d[^>]*>([\s\S]*?)</h\d>'
            ]:
                tm = re.search(pat, item, re.I)
                if tm:
                    t = re.sub(r'<[^>]+>', '', tm.group(1)).strip()
                    if t and t.lower() not in ("search", "top-1", "top-2", "top-3", "top", "more"):
                        title = t
                        break

            if not title:
                text_candidates = re.findall(r'>([^<>]+)<', item)
                for tc in text_candidates:
                    tc_clean = tc.strip()
                    if len(tc_clean) >= 4 and not re.match(r'^\d{1,2}:\d{2}', tc_clean) and tc_clean.lower() not in ("search", "top-1"):
                        title = tc_clean
                        break

            pic = ""
            for pat in [
                r'data-src=["\']([^"\']+)["\']',
                r'data-original=["\']([^"\']+)["\']',
                r'data-cover=["\']([^"\']+)["\']',
                r'src=["\']([^"\']+)["\']'
            ]:
                pm = re.search(pat, item, re.I)
                if pm:
                    p = pm.group(1).strip()
                    if p and not any(bad in p for bad in (".svg", ".ico", "sr-", "logo", "avatar", "default", "loading")):
                        pic = p
                        break

            duration = ""
            for dpat in [
                r'class=["\'][^"\']*(?:duration|time|tag|badge|rounded-large)[^"\']*["\'][^>]*>([\s\S]*?)<',
                r'>(\d{1,2}:\d{2}(?::\d{2})?)<'
            ]:
                dm = re.search(dpat, item, re.I)
                if dm:
                    duration = re.sub(r'<[^>]+>', '', dm.group(1)).strip()
                    break

            if title:
                seen_ids.add(href)
                cards.append({
                    "vod_id": href,
                    "vod_name": title,
                    "vod_pic": self._build_proxy_pic(pic),
                    "vod_remarks": format_remarks("ZakaTV", duration),
                    "style": {"type": "rect", "ratio": 1.78}
                })

        return cards

    def categoryContent(self, tid, pg, filter=None, extend=None):
        target_path = str(tid)
        page_int = int(pg) if str(pg).isdigit() else 1
        page_url = target_path
        if page_int > 1:
            if page_url.endswith("/"):
                page_url = "%spage/%d/" % (page_url, page_int)
            else:
                page_url = "%s?page=%d" % (page_url, page_int)

        res = self._fetch(page_url, referer=self.siteUrl)
        html = res.get("text", "")
        cards = self._parse_card_list(html)

        return {
            "list": cards,
            "page": page_int,
            "pagecount": 9999 if cards else 1,
            "limit": len(cards),
            "total": 99999
        }

    def detailContent(self, ids):
        raw_id = ids[0] if ids else ""
        target_path = str(raw_id).strip()
        if not target_path.startswith("http"):
            target_url = self.siteUrl + ("/" + target_path.lstrip("/"))
        else:
            target_url = target_path

        res = self._fetch(target_url, referer=self.siteUrl + "/")
        html = res.get("text", "")

        title_m = re.search(r'<h1[^>]*>([\s\S]*?)</h1>', html, re.I)
        if not title_m:
            title_m = re.search(r'<title>([^<|]+)', html)
        title = re.sub(r'<[^>]+>', '', title_m.group(1)).strip() if title_m else "正片"

        desc = ""
        desc_m = re.search(r'<meta\s+name=["\']description["\']\s+content=["\']([^"\']+)["\']', html, re.I)
        if desc_m:
            desc = desc_m.group(1).strip()

        pic = ""
        pic_m = re.search(r'<meta\s+property=["\']og:image["\']\s+content=["\']([^"\']+)["\']', html, re.I)
        if pic_m:
            pic = pic_m.group(1).strip()

        embed_match = re.search(r'/videos/embed\?id=(\d+)', html)
        embed_id = embed_match.group(1) if embed_match else ""

        if embed_id:
            play_target = "%s/videos/embed?id=%s" % (self.siteUrl, embed_id)
        else:
            play_target = target_url

        full_desc = "【🔥 官方交流群: %s】\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n%s" % (self.tgGroup, desc)

        vod = {
            "vod_id": target_path,
            "vod_name": title,
            "vod_pic": self._build_proxy_pic(pic),
            "vod_actor": self.brandActor,
            "vod_director": self.brandDirector,
            "vod_remarks": format_remarks("ZakaTV", "正片"),
            "vod_content": full_desc,
            "vod_play_from": "Zaka专线",
            "vod_play_url": "超清正片$" + play_target
        }
        return {"list": [vod]}

    def playerContent(self, flag, id, vipFlags=None):
        target_url = str(id).strip()
        res = self._fetch(target_url, referer=self.siteUrl + "/")
        html = res.get("text", "")

        m3u8_matches = re.findall(r'["\'](https?://[^"\']*\.m3u8[^"\']*)["\']', html, re.I)
        headers = {
            "User-Agent": self._ua,
            "Referer": self.siteUrl + "/"
        }

        if m3u8_matches:
            return {
                "parse": 0,
                "playUrl": "",
                "url": m3u8_matches[0],
                "header": headers
            }

        return {
            "parse": 1,
            "playUrl": "",
            "url": target_url,
            "header": headers
        }

    def searchContent(self, key, quick=False, pg="1"):
        search_path = "/videos/search/%s/" % urllib.parse.quote(str(key).strip())
        page_int = int(pg) if str(pg).isdigit() else 1
        if page_int > 1:
            search_path = "%spage/%d/" % (search_path, page_int)
        
        res = self._fetch(search_path, referer=self.siteUrl)
        html = res.get("text", "")
        cards = self._parse_card_list(html)
        return {
            "list": cards,
            "page": page_int,
            "pagecount": 9999 if cards else 1,
            "limit": len(cards),
            "total": 99999
        }

    def liveContent(self):
        return ""

    def action(self, action):
        return {"msg": "ok"}

    def localProxy(self, params):
        u_b64 = params.get("u", "")
        if not u_b64:
            return [404, "text/plain; charset=utf-8", "Missing URL parameter"]
        try:
            pad = len(u_b64) % 4
            if pad:
                u_b64 += "=" * (4 - pad)
            real_url = base64.urlsafe_b64decode(u_b64.encode("ascii")).decode("utf-8")
        except Exception:
            return [400, "text/plain; charset=utf-8", "Invalid URL Base64"]

        res = self._fetch(real_url, referer=self.siteUrl + "/")
        raw_bytes = res.get("bytes", b"")
        if not raw_bytes:
            return [res.get("code", 502), "text/plain; charset=utf-8", "Upstream Error"]

        decrypted = decrypt_image_payload(raw_bytes)
        return [200, "image/jpeg", decrypted]

    def manualVideoCheck(self):
        return False

    def isVideoFormat(self, url):
        low = (url or "").lower()
        if any(bad in low for bad in ("preview.mp4", "sample.mp4", "trailer.mp4")):
            return False
        return any(k in low for k in (".m3u8", ".mp4", "streamhls", "master.m3u8", ".flv", ".ts"))

    def destroy(self):
        pass
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import re
import json
import base64
import hashlib
import urllib.request
import urllib.parse
from urllib.parse import quote, unquote
import http.cookiejar
import gzip
import zlib
import ssl

try:
    from base.spider import Spider as SpiderBase
except ImportError:
    class SpiderBase(object):
        def getCache(self, key): return None
        def setCache(self, key, value): return "fail"
        def delCache(self, key): return "fail"

try:
    from Crypto.Cipher import AES as FastAES
except Exception:
    FastAES = None

class PureAES(object):
    S_BOX = [
        0x63, 0x7C, 0x77, 0x7B, 0xF2, 0x6B, 0x6F, 0xC5, 0x30, 0x01, 0x67, 0x2B, 0xFE, 0xD7, 0xAB, 0x76,
        0xCA, 0x82, 0xC9, 0x7D, 0xFA, 0x59, 0x47, 0xF0, 0xAD, 0xD4, 0xA2, 0xAF, 0x9C, 0xA4, 0x72, 0xC0,
        0xB7, 0xFD, 0x93, 0x26, 0x36, 0x3F, 0xF7, 0xCC, 0x34, 0xA5, 0xE5, 0xF1, 0x71, 0xD8, 0x31, 0x15,
        0x04, 0xC7, 0x23, 0xC3, 0x18, 0x96, 0x05, 0x9A, 0x07, 0x12, 0x80, 0xE2, 0xEB, 0x27, 0xB2, 0x75,
        0x09, 0x83, 0x2C, 0x1A, 0x1B, 0x6E, 0x5A, 0xA0, 0x52, 0x3B, 0xD6, 0xB3, 0x29, 0xE3, 0x2F, 0x84,
        0x53, 0xD1, 0x00, 0xED, 0x20, 0xFC, 0xB1, 0x5B, 0x6A, 0xCB, 0xBE, 0x39, 0x4A, 0x4C, 0x58, 0xCF,
        0xD0, 0xEF, 0xAA, 0xFB, 0x43, 0x4D, 0x33, 0x85, 0x45, 0xF9, 0x02, 0x7F, 0x50, 0x3C, 0x9F, 0xA8,
        0x51, 0xA3, 0x40, 0x8F, 0x92, 0x9D, 0x38, 0xF5, 0xBC, 0xB6, 0xDA, 0x21, 0x10, 0xFF, 0xF3, 0xD2,
        0xCD, 0x0C, 0x13, 0xEC, 0x5F, 0x97, 0x44, 0x17, 0xC4, 0xA7, 0x7E, 0x3D, 0x64, 0x5D, 0x19, 0x73,
        0x60, 0x81, 0x4F, 0xDC, 0x22, 0x2A, 0x90, 0x88, 0x46, 0xEE, 0xB8, 0x14, 0xDE, 0x5E, 0x0B, 0xDB,
        0xE0, 0x32, 0x3A, 0x0A, 0x49, 0x06, 0x24, 0x5C, 0xC2, 0xD3, 0xAC, 0x62, 0x91, 0x95, 0xE4, 0x79,
        0xE7, 0xC8, 0x37, 0x6D, 0x8D, 0xD5, 0x4E, 0xA9, 0x6C, 0x56, 0xF4, 0xEA, 0x65, 0x7A, 0xAE, 0x08,
        0xBA, 0x78, 0x25, 0x2E, 0x1C, 0xA6, 0xB4, 0xC6, 0xE8, 0xDD, 0x74, 0x1F, 0x4B, 0xBD, 0x8B, 0x8A,
        0x70, 0x3E, 0xB5, 0x66, 0x48, 0x03, 0xF6, 0x0E, 0x61, 0x35, 0x57, 0xB9, 0x86, 0xC1, 0x1D, 0x9E,
        0xE1, 0xF8, 0x98, 0x11, 0x69, 0xD9, 0x8E, 0x94, 0x9B, 0x1E, 0x87, 0xE9, 0xCE, 0x55, 0x28, 0xDF,
        0x8C, 0xA1, 0x89, 0x0D, 0xBF, 0xE6, 0x42, 0x68, 0x41, 0x99, 0x2D, 0x0F, 0xB0, 0x54, 0xBB, 0x16
    ]
    INV_S_BOX = [0] * 256
    RCON = [0x00, 0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36]

    @classmethod
    def _init_tables(cls):
        if cls.INV_S_BOX[0x63] == 0:
            for i, v in enumerate(cls.S_BOX):
                cls.INV_S_BOX[v] = i

    def __init__(self, key):
        self._init_tables()
        self.key = list(key)
        self.nk = len(self.key) // 4
        self.nr = self.nk + 6
        self.w = self._key_expansion()

    def _sub_word(self, w):
        return [self.S_BOX[b] for b in w]

    def _rot_word(self, w):
        return w[1:] + w[:1]

    def _key_expansion(self):
        w = []
        for i in range(self.nk):
            w.append(self.key[4*i : 4*i + 4])
        for i in range(self.nk, 4 * (self.nr + 1)):
            temp = list(w[i - 1])
            if i % self.nk == 0:
                temp = [b ^ r for b, r in zip(self._sub_word(self._rot_word(temp)), [self.RCON[i // self.nk], 0, 0, 0])]
            elif self.nk > 6 and i % self.nk == 4:
                temp = self._sub_word(temp)
            w.append([a ^ b for a, b in zip(w[i - self.nk], temp)])
        return w

    @staticmethod
    def _xt(a):
        return ((a << 1) ^ 0x1B) & 0xFF if a & 0x80 else (a << 1)

    @classmethod
    def _mul(cls, a, b):
        res = 0
        while b:
            if b & 1:
                res ^= a
            a = cls._xt(a)
            b >>= 1
        return res

    def _inv_mix_columns(self, s):
        for c in range(4):
            col = [s[r][c] for r in range(4)]
            s[0][c] = self._mul(col[0], 0x0E) ^ self._mul(col[1], 0x0B) ^ self._mul(col[2], 0x0D) ^ self._mul(col[3], 0x09)
            s[1][c] = self._mul(col[0], 0x09) ^ self._mul(col[1], 0x0E) ^ self._mul(col[2], 0x0B) ^ self._mul(col[3], 0x0D)
            s[2][c] = self._mul(col[0], 0x0D) ^ self._mul(col[1], 0x09) ^ self._mul(col[2], 0x0E) ^ self._mul(col[3], 0x0B)
            s[3][c] = self._mul(col[0], 0x0B) ^ self._mul(col[1], 0x0D) ^ self._mul(col[2], 0x09) ^ self._mul(col[3], 0x0E)

    def decrypt_block(self, in_bytes):
        s = [[in_bytes[r + 4 * c] for c in range(4)] for r in range(4)]
        for r in range(4):
            for c in range(4):
                s[r][c] ^= self.w[self.nr * 4 + c][r]
        for round_idx in range(self.nr - 1, 0, -1):
            s[1] = s[1][3:] + s[1][:3]
            s[2] = s[2][2:] + s[2][:2]
            s[3] = s[3][1:] + s[3][:1]
            for r in range(4):
                for c in range(4):
                    s[r][c] = self.INV_S_BOX[s[r][c]]
            for r in range(4):
                for c in range(4):
                    s[r][c] ^= self.w[round_idx * 4 + c][r]
            self._inv_mix_columns(s)
        s[1] = s[1][3:] + s[1][:3]
        s[2] = s[2][2:] + s[2][:2]
        s[3] = s[3][1:] + s[3][:1]
        for r in range(4):
            for c in range(4):
                s[r][c] = self.INV_S_BOX[s[r][c]]
        for r in range(4):
            for c in range(4):
                s[r][c] ^= self.w[c][r]
        out = bytearray(16)
        for r in range(4):
            for c in range(4):
                out[r + 4 * c] = s[r][c]
        return bytes(out)

    def decrypt_cbc(self, ciphertext, iv):
        blocks = [ciphertext[i:i+16] for i in range(0, len(ciphertext), 16)]
        plaintext = bytearray()
        prev = iv
        for block in blocks:
            dec = self.decrypt_block(block)
            plaintext.extend([a ^ b for a, b in zip(dec, prev)])
            prev = block
        pad = plaintext[-1]
        if 1 <= pad <= 16:
            return bytes(plaintext[:-pad])
        return bytes(plaintext)

def format_remarks(brand="ZakaTV", meta=""):
    clean_meta = str(meta or "").strip()
    clean_meta = re.sub(r"[\r\n\t]+", " ", clean_meta).strip()
    if clean_meta:
        return "%s | %s" % (brand, clean_meta)
    return brand

PALETTE_BG = [
    "1e1b4b", "4c0519", "14532d", "451a03",
    "3b0764", "0c4a6e", "701a75", "18181b"
]

def generate_brand_poster(title, ratio_type="rect_v"):
    clean_title = re.sub(r'[\r\n\t\+]+', ' ', title or '').strip()
    words = clean_title.split()
    if len(words) >= 2:
        display_text = "%s %s" % (words[0], words[1])
    else:
        display_text = clean_title[:10]
    hash_val = sum(ord(c) for c in clean_title)
    bg_color = PALETTE_BG[hash_val % len(PALETTE_BG)]
    size = "600x338" if ratio_type == "rect_h" else "400x600"
    full_text = "%s\n[ ZakaTV ]" % display_text
    return "https://dummyimage.com/%s/%s/ffffff.png&text=%s" % (size, bg_color, quote(full_text))

class Spider(SpiderBase):
    def __init__(self):
        super(Spider, self).__init__()
        self.siteUrl = "https://www.fulleroticmovies.net"
        self.tgGroup = "https://t.me/+3t5XRPPo9mlkZDRl"
        self.brandActor = "📺TG群: https://t.me/+3t5XRPPo9mlkZDRl"
        self.brandDirector = "📺ZakaTV"
        self._ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        self._ok_api = "https://api.ok.ru/fb.do"
        self.options = {}

        self.ctx = ssl.create_default_context()
        self.ctx.check_hostname = False
        self.ctx.verify_mode = ssl.CERT_NONE

        self.cj = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cj),
            urllib.request.HTTPSHandler(context=self.ctx)
        )

        self.mainSortSeq = ["newest", "trending", "most-viewed", "top-rated"]
        self.mainSortNames = {
            "newest": "最新",
            "trending": "热门",
            "most-viewed": "浏览量最高",
            "top-rated": "评分最高"
        }
        self.mainSortRoutes = {
            "newest": "/videos/",
            "trending": "/trending/",
            "most-viewed": "/most-viewed/",
            "top-rated": "/top-rated/"
        }

        self.catRealSubRoutes = {
            "newest": "",
            "most-viewed": "most-popular/",
            "top-rated": "top-rated/"
        }

        self.promotedCatList = [
            ("cat_70s", "70年代", "70s"),
            ("cat_80s", "80年代", "80s"),
            ("cat_90s", "90年代", "90s"),
            ("cat_plot", "情节导向", "plot-oriented"),
            ("cat_lesbian", "女同性恋", "lesbian"),
            ("cat_asian", "跨种族-亚洲女孩", "interracial-asian-girls"),
            ("cat_vintage", "历史时代作品", "vintage-period-pieces"),
            ("cat_family", "家庭角色扮演", "family-roleplay"),
            ("cat_star", "经典明星展示", "classic-star-showcase"),
            ("cat_bigtits", "大胸", "big-tits"),
            ("cat_bigdicks", "大阴茎", "big-dicks"),
            ("cat_avn", "AVN获奖作品", "avn-award-winners")
        ]

        self.promotedCatDict = {item[0]: item[2] for item in self.promotedCatList}

        self.promotedSlugSet = {
            "70s", "80s", "90s", "plot-oriented", "lesbian",
            "interracial-asian-girls", "vintage-period-pieces",
            "family-roleplay", "classic-star-showcase",
            "big-tits", "big-dicks", "avn-award-winners"
        }

    def init(self, extend=""):
        if isinstance(extend, dict):
            self.options = extend
        elif extend:
            try:
                self.options = json.loads(extend)
            except Exception:
                self.options = {}
        return True

    def getName(self):
        return "ZakaTV·FullErotic"

    def isVideoFormat(self, url):
        return ".mp4" in (url or "").lower() or ".m3u8" in (url or "").lower()

    def manualVideoCheck(self):
        return False

    def _fetch_raw(self, target_url, referer=""):
        if not target_url:
            return {"code": 0, "text": "", "bytes": b"", "err": "", "final_url": "", "headers": {}}
        if target_url.startswith("//"):
            target_url = "https:" + target_url
        elif target_url.startswith("/"):
            target_url = self.siteUrl + target_url

        headers = {
            "User-Agent": self._ua,
            "Referer": referer if referer else (self.siteUrl + "/"),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive"
        }

        for attempt in range(2):
            try:
                req = urllib.request.Request(target_url, headers=headers)
                with self.opener.open(req, timeout=15) as resp:
                    raw = resp.read()
                    resp_headers = dict(resp.headers) if hasattr(resp, "headers") else {}
                    enc = resp_headers.get("Content-Encoding", "").lower()
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
                    return {"code": resp.getcode(), "text": text, "bytes": raw, "err": "", "final_url": resp.geturl(), "headers": resp_headers}
            except Exception as e:
                if attempt == 0:
                    continue
                return {"code": -1, "text": "", "bytes": b"", "err": str(e), "final_url": target_url, "headers": {}}
        return {"code": -1, "text": "", "bytes": b"", "err": "timeout", "final_url": target_url, "headers": {}}

    def _clean_text(self, text):
        return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', text or '')).strip()

    def homeContent(self, filter):
        classes = [{"type_name": "精选影视", "type_id": "root_videos"}]

        for cid, cname, _ in self.promotedCatList:
            classes.append({"type_name": cname, "type_id": cid})

        classes.extend([
            {"type_name": "全部题材(450+)", "type_id": "categories"},
            {"type_name": "制片厂牌", "type_id": "studios"},
            {"type_name": "演职人员", "type_id": "pornstars"}
        ])

        filters = {}
        if filter:
            filters["root_videos"] = [
                {
                    "key": "sub_type",
                    "name": "频道筛选",
                    "value": [
                        {"n": "最新视频", "v": "newest"},
                        {"n": "趋势热门", "v": "trending"},
                        {"n": "最多观看", "v": "most-viewed"},
                        {"n": "高分精选", "v": "top-rated"}
                    ]
                }
            ]

            cat_filter_items = [
                {
                    "key": "cat_sort",
                    "name": "排序筛选",
                    "value": [
                        {"n": "最新", "v": "newest"},
                        {"n": "浏览量最高", "v": "most-viewed"},
                        {"n": "评分最高", "v": "top-rated"}
                    ]
                }
            ]
            for cid, _, _ in self.promotedCatList:
                filters[cid] = cat_filter_items

        return {"class": classes, "filters": filters}

    def homeVideoContent(self):
        return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        slug = str(tid).strip("/")
        p = int(pg) if pg else 1
        extend = extend or {}

        # 1. 精选影视 (统一为 0.75 竖版海报)
        if slug == "root_videos" or slug.startswith("ctrl_video@@"):
            if slug.startswith("ctrl_video@@"):
                cur_sort = slug.split("ctrl_video@@", 1)[1]
            else:
                cur_sort = extend.get("sub_type", "newest")

            if cur_sort not in self.mainSortSeq:
                cur_sort = "newest"

            route = self.mainSortRoutes.get(cur_sort, "/videos/")
            target_url = urllib.parse.urljoin(self.siteUrl, route)
            if p > 1:
                target_url = "%s?page=%d" % (target_url, p)

            res = self._fetch_raw(target_url)
            feed_data = self._parse_video_feed(res.get("text", ""), p, ratio=0.75)

            if p == 1:
                cur_idx = self.mainSortSeq.index(cur_sort)
                next_idx = (cur_idx + 1) % len(self.mainSortSeq)
                next_sort = self.mainSortSeq[next_idx]

                cur_name = self.mainSortNames[cur_sort]
                next_name = self.mainSortNames[next_sort]

                control_card = {
                    "vod_id": "ctrl_video@@" + next_sort,
                    "vod_name": "🔀 状态轮转: %s (点击切换)" % cur_name,
                    "vod_pic": "https://dummyimage.com/400x600/991b1b/ffffff.png&text=%s" % quote("当前: %s\n[ ZakaTV ]" % cur_name),
                    "vod_remarks": "切至: %s" % next_name,
                    "vod_tag": "folder",
                    "style": {"type": "rect", "ratio": 0.75}
                }
                feed_data["list"].insert(0, control_card)
            return feed_data

        # 2. 12 个核心题材主分类视频列表 (统一为 0.75 竖版海报)
        if slug in self.promotedCatDict:
            cat_slug = self.promotedCatDict[slug]
            cat_sort = extend.get("cat_sort", "newest")
            sub_route = self.catRealSubRoutes.get(cat_sort, "").strip("/")

            # 组装基础路径: /category/{cat_slug} 或 /category/{cat_slug}/{sub_route}
            base_parts = ["/category", cat_slug]
            if sub_route:
                base_parts.append(sub_route)
            
            # 翻页时追加页码路径，如 /category/70s/2/ 或 /category/70s/most-popular/2/
            if p > 1:
                base_parts.append(str(p))
            
            target_path = "/".join(base_parts) + "/"
            target_url = urllib.parse.urljoin(self.siteUrl, target_path)

            res = self._fetch_raw(target_url)
            return self._parse_video_feed(res.get("text", ""), p, ratio=0.75)

        # 3. 二级下钻视频瀑布流 (统一为 0.75 竖版海报)
        if slug.startswith("folder@@"):
            target_sub_url = slug.split("folder@@", 1)[1]
            if not target_sub_url.startswith("http"):
                target_sub_url = urllib.parse.urljoin(self.siteUrl, target_sub_url)
            
            if p > 1:
                if "/category/" in target_sub_url or "/studio/" in target_sub_url or "/pornstar/" in target_sub_url:
                    # 静态路径格式：去掉末尾斜杠后拼上 /页码/
                    clean_base = target_sub_url.rstrip("/")
                    target_sub_url = "%s/%d/" % (clean_base, p)
                else:
                    # 兜底查询参数
                    sep = "&" if "?" in target_sub_url else "?"
                    target_sub_url = "%s%spage=%d" % (target_sub_url, sep, p)

            res = self._fetch_raw(target_sub_url)
            return self._parse_video_feed(res.get("text", ""), p, ratio=0.75)

        # 4. 全部题材一级页 (强制统一为 1.78 横向海报)
        if slug == "categories":
            target_url = urllib.parse.urljoin(self.siteUrl, "/categories/")
            if p > 1:
                target_url = "%s?page=%d" % (target_url, p)
            res = self._fetch_raw(target_url)
            html = res.get("text", "")
            scoped_html = re.sub(r'<(header|nav|aside)[\s\S]*?</\1>', '', html, flags=re.I)

            cat_links = re.findall(r'<a[^>]+href=["\']([^"\']*/category/([^/"\']+)/?)["\'][^>]*>([\s\S]*?)</a>', scoped_html, re.I)
            v_list = []
            seen_hrefs = set()
            for full_href, cat_part, body in cat_links:
                c_slug = cat_part.strip().lower()
                if c_slug in self.promotedSlugSet:
                    continue
                if full_href in seen_hrefs:
                    continue
                seen_hrefs.add(full_href)

                full_t = self._clean_text(body)
                if not full_t or len(full_t) < 2:
                    continue

                num_m = re.search(r'(\d+)$', full_t)
                meta_num = num_m.group(1) if num_m else ""
                clean_title = re.sub(r'\s*\d+$', '', full_t).strip() or full_t

                pic_card = generate_brand_poster(clean_title, "rect_h")
                remarks = ("ZakaTV · %s部" % meta_num) if meta_num else "ZakaTV · 题材"

                v_list.append({
                    "vod_id": "folder@@" + full_href,
                    "vod_name": clean_title,
                    "vod_pic": pic_card,
                    "vod_remarks": remarks,
                    "vod_tag": "folder",
                    "style": {"type": "rect", "ratio": 1.78}
                })

            return {
                "page": p,
                "pagecount": 1,
                "limit": len(v_list),
                "total": len(v_list),
                "list": v_list
            }

        # 5. 制片厂牌一级页 (强制统一为 1.78 横向海报)
        if slug == "studios":
            target_url = urllib.parse.urljoin(self.siteUrl, "/studios/")
            if p > 1:
                target_url = "%s?page=%d" % (target_url, p)
            res = self._fetch_raw(target_url)
            return self._parse_folder_list(res.get("text", ""), p, "/studio/", "厂牌", 32, ratio=1.78)

        # 6. 演职人员一级页 (强制统一为 0.75 竖版海报)
        if slug == "pornstars":
            target_url = urllib.parse.urljoin(self.siteUrl, "/pornstars/")
            if p > 1:
                target_url = "%s?page=%d" % (target_url, p)
            res = self._fetch_raw(target_url)
            return self._parse_folder_list(res.get("text", ""), p, "/pornstar/", "演员", 10, ratio=0.75)

        return {"page": p, "pagecount": 1, "limit": 0, "total": 0, "list": []}

    def _parse_folder_list(self, html, p, target_pattern, default_tag, max_pages, ratio=1.78):
        scoped_html = re.sub(r'<(header|nav|aside)[\s\S]*?</\1>', '', html or '', flags=re.I)
        card_chunks = re.findall(r'<div[^>]+class=["\'][^"\']*(?:item|col-|thumb|actor|studio|model)[^"\']*["\'][\s\S]*?</div>\s*</div>', scoped_html, re.I)
        if not card_chunks:
            card_chunks = re.findall(r'<a[^>]+href=["\'][^"\']*' + re.escape(target_pattern) + r'[^"\']+["\'][\s\S]*?</a>', scoped_html, re.I)

        v_list = []
        seen_hrefs = set()

        for chunk in card_chunks:
            href_m = re.search(r'<a[^>]+href=["\']([^"\']*' + re.escape(target_pattern) + r'[^"\']+)["\']', chunk, re.I)
            if not href_m:
                continue
            href = href_m.group(1).strip()
            if href in seen_hrefs:
                continue

            pic_m = re.search(r'<img[^>]+(?:data-src|data-original|src)=["\']([^"\']+)["\']', chunk, re.I)
            pic = pic_m.group(1).strip() if pic_m else ""
            if pic.startswith("//"):
                pic = "https:" + pic
            elif pic.startswith("/"):
                pic = self.siteUrl + pic

            title_m = re.search(r'title=["\']([^"\']+)["\']', chunk, re.I)
            if not title_m:
                title_m = re.search(r'<img[^>]+alt=["\']([^"\']+)["\']', chunk, re.I)
            title = self._clean_text(title_m.group(1)) if title_m else self._clean_text(chunk)
            if not title or len(title) < 2:
                continue

            meta_match = re.search(r'([0-9]{1,5})\s*(?:Videos|部|movies)', chunk, re.I)
            if not meta_match:
                meta_match = re.search(r'(?:>|\s)([0-9]{1,4})\s*(?:部)?(?:\s*<|$)', chunk)

            if meta_match:
                raw_num = meta_match.group(1).strip()
                meta_str = "%s部" % raw_num
            else:
                meta_str = default_tag

            is_valid_image = pic and not any(bad in pic.lower() for bad in ("blank.gif", "pixel.gif", "spacer.gif"))
            if not is_valid_image:
                ratio_type = "rect_h" if ratio >= 1.0 else "rect_v"
                pic = generate_brand_poster(title, ratio_type)

            seen_hrefs.add(href)
            remarks = "ZakaTV · %s" % meta_str

            v_list.append({
                "vod_id": "folder@@" + href,
                "vod_name": title,
                "vod_pic": pic,
                "vod_remarks": remarks,
                "vod_tag": "folder",
                "style": {"type": "rect", "ratio": ratio}
            })

        pagecount = max_pages if len(v_list) >= 12 else p
        return {
            "page": p,
            "pagecount": pagecount,
            "limit": len(v_list),
            "total": pagecount * len(v_list),
            "list": v_list
        }

    def _parse_video_feed(self, html, p, ratio=0.75):
        scoped_html = re.sub(r'<(header|nav|aside)[\s\S]*?</\1>', '', html or '', flags=re.I)
        card_chunks = re.findall(r'<div[^>]+class=["\'][^"\']*(?:item|video|col-|thumb)[^"\']*["\'][\s\S]*?</div>\s*</div>', scoped_html, re.I)
        if not card_chunks:
            card_chunks = re.findall(r'<a[^>]+href=["\'][^"\']*/video/[^"\']+["\'][\s\S]*?</a>', scoped_html, re.I)

        v_list = []
        seen_hrefs = set()

        for chunk in card_chunks:
            href_m = re.search(r'<a[^>]+href=["\']([^"\']*/video/[^"\']+)["\']', chunk, re.I)
            if not href_m:
                continue
            href = href_m.group(1).strip()
            if href in seen_hrefs:
                continue

            pic_m = re.search(r'<img[^>]+(?:data-src|data-original|src)=["\']([^"\']+)["\']', chunk, re.I)
            pic = pic_m.group(1).strip() if pic_m else ""
            if not pic:
                continue
            if pic.startswith("//"):
                pic = "https:" + pic
            elif pic.startswith("/"):
                pic = self.siteUrl + pic

            title_m = re.search(r'title=["\']([^"\']+)["\']', chunk, re.I)
            if not title_m:
                title_m = re.search(r'<img[^>]+alt=["\']([^"\']+)["\']', chunk, re.I)
            title = self._clean_text(title_m.group(1)) if title_m else self._clean_text(chunk)
            if not title or len(title) < 2:
                continue

            dur_m = re.search(r'<span[^>]+class=["\'][^"\']*(?:duration|time)[^"\']*["\'][^>]*>([\s\S]*?)</span>', chunk, re.I)
            duration = self._clean_text(dur_m.group(1)) if dur_m else ""

            seen_hrefs.add(href)
            v_list.append({
                "vod_id": href,
                "vod_name": title,
                "vod_pic": pic,
                "vod_remarks": format_remarks("ZakaTV", duration or "正片"),
                "style": {"type": "rect", "ratio": ratio}
            })

        pagecount = (p + 1) if len(v_list) >= 15 else p
        return {
            "page": p,
            "pagecount": pagecount,
            "limit": len(v_list),
            "total": 999 if pagecount > p else len(v_list),
            "list": v_list
        }

    def _decrypt_session_key(self, encrypted_b64, password):
        try:
            info = json.loads(base64.b64decode(encrypted_b64).decode("utf-8"))
            salt = bytes.fromhex(info["salt"])
            iv = bytes.fromhex(info["iv"])
            iterations = int(info.get("iterations") or 999)
            ciphertext = base64.b64decode(info["ciphertext"])

            key = hashlib.pbkdf2_hmac("sha512", password.encode("utf-8"), salt, iterations, 32)

            if FastAES is not None:
                cipher = FastAES.new(key, FastAES.MODE_CBC, iv)
                plain = cipher.decrypt(ciphertext)
                pad = plain[-1]
                if 1 <= pad <= 16:
                    return plain[:-pad].decode("utf-8")
                return plain.decode("utf-8")
            else:
                pure_aes = PureAES(key)
                plain = pure_aes.decrypt_cbc(ciphertext, iv)
                return plain.decode("utf-8")
        except Exception:
            return ""

    def _resolve_ok_streams(self, encrypted_b64, password, ok_video_id):
        session_key = self._decrypt_session_key(encrypted_b64, password)
        if not session_key:
            return []

        fields = "video.url_tiny,video.url_low,video.url_high,video.url_medium,video.url_quadhd,video.url_mobile,video.url_ultrahd,video.url_fullhd"
        params = {
            "application_key": "CBAFJIICABABABABA",
            "fields": fields,
            "method": "video.get",
            "session_key": session_key,
            "vids": str(ok_video_id)
        }
        api_req_url = "%s?%s" % (self._ok_api, urllib.parse.urlencode(params))
        try:
            req = urllib.request.Request(api_req_url, headers={
                "User-Agent": self._ua,
                "Accept": "application/json"
            })
            with self.opener.open(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                video_obj = data.get("videos", [{}])[0]
                q_map = [
                    ("url_ultrahd", "4K超清"),
                    ("url_fullhd", "1080P超清"),
                    ("url_quadhd", "720P高清"),
                    ("url_high", "标清540P"),
                    ("url_medium", "标清480P"),
                    ("url_low", "标清360P"),
                    ("url_mobile", "移动端流")
                ]
                streams = []
                for k, name in q_map:
                    if video_obj.get(k):
                        streams.append((name, video_obj[k]))
                return streams
        except Exception:
            return []

    def detailContent(self, ids):
        raw_id = ids[0] if isinstance(ids, (list, tuple)) else str(ids)
        target_url = str(raw_id).strip()

        if target_url.startswith("ctrl_video@@") or target_url.startswith("folder@@"):
            return self.categoryContent(target_url, 1, None, None)

        if not target_url.startswith("http"):
            target_url = urllib.parse.urljoin(self.siteUrl, target_url)

        res = self._fetch_raw(target_url)
        html = res.get("text", "")

        title_m = re.search(r'<title>(.*?)</title>', html, re.I)
        raw_title = title_m.group(1).strip() if title_m else "Zaka精选影片"
        clean_name = re.sub(r'\s*-\s*Full Erotic.*$', '', raw_title, flags=re.I).strip()
        clean_name = re.sub(r'Watch Online.*?:', '', clean_name, flags=re.I).strip()
        if not clean_name:
            clean_name = raw_title

        pic_m = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', html, re.I)
        if not pic_m:
            pic_m = re.search(r'["\'](https?://[^"\']*/thumb/[^"\']*\.webp)["\']', html, re.I)
        pic = pic_m.group(1).strip() if pic_m else ""

        desc_m = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']', html, re.I)
        desc_text = self._clean_text(desc_m.group(1)) if desc_m else ""

        full_desc = (
            "【🔥 官方交流群: %s】\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "%s"
        ) % (self.tgGroup, desc_text if desc_text else "Zaka专线 官方正片 极速秒播")
        escaped_desc = full_desc.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        mp4_m = re.search(r"generate_mp4\('([^']+)',\s*'([^']+)',\s*'([^']+)',\s*'([^']+)'\)", html)
        play_pairs = []

        if mp4_m:
            encrypted, password, ok_video_id, _ = mp4_m.groups()
            streams = self._resolve_ok_streams(encrypted, password, ok_video_id)
            for q_name, cdn_url in streams:
                play_pairs.append("%s$%s" % (q_name, cdn_url))

        if play_pairs:
            vod_play_from = "Zaka专线"
            vod_play_url = "#".join(play_pairs)
        else:
            vod_play_from = "Zaka专线"
            vod_play_url = "超清正片$%s" % target_url

        vod = {
            "vod_id": target_url,
            "vod_name": clean_name,
            "vod_pic": pic,
            "vod_actor": self.brandActor,
            "vod_director": self.brandDirector,
            "vod_remarks": format_remarks("ZakaTV", "超清正片"),
            "vod_content": escaped_desc,
            "vod_play_from": vod_play_from,
            "vod_play_url": vod_play_url
        }
        return {"list": [vod]}

    def playerContent(self, flag, id, vipFlags):
        target_play_url = str(id).strip()

        if target_play_url.startswith("http"):
            headers = {
                "User-Agent": self._ua,
                "Referer": self.siteUrl + "/"
            }
            if any(k in target_play_url for k in ("mycdn.me", "vkuser.net", "ok.ru", "vk.com", "googlevideo.com")):
                headers.pop("Referer", None)

            return {
                "parse": 0,
                "playUrl": "",
                "url": target_play_url,
                "header": headers
            }

        return {
            "parse": 1,
            "playUrl": "",
            "url": target_play_url,
            "header": {"User-Agent": self._ua}
        }

    def searchContent(self, key, quick, pg="1"):
        p = int(pg) if pg else 1
        search_url = "%s/search/?q=%s&page=%d" % (self.siteUrl, quote(key), p)
        res = self._fetch_raw(search_url)
        return self._parse_video_feed(res.get("text", ""), p, ratio=0.75)

    def action(self, action):
        return {"msg": "ok"}

    def liveContent(self):
        return ""

    def localProxy(self, params):
        return [404, "text/plain; charset=utf-8", "Proxy not configured"]

    def destroy(self):
        self.options = {}

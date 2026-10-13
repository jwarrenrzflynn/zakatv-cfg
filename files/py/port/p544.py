# -*- coding: utf-8 -*-
import sys
import json
import ssl
import gzip
import zlib
import re
from urllib import request, parse, error

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        pass

# 1. 优先尝试导入运行环境的原生 C 加密库 (5ms 极速起步)
FAST_AES = None
try:
    from Cryptodome.Cipher import AES as CryptodomeAES
    FAST_AES = CryptodomeAES
except Exception:
    try:
        from Crypto.Cipher import AES as CryptoAES
        FAST_AES = CryptoAES
    except Exception:
        FAST_AES = None

# 2. 查表加速版 PureAES (纯标准库，无需任何外部依赖)
class FastPureAES(object):
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

    Td0 = [0] * 256
    Td1 = [0] * 256
    Td2 = [0] * 256
    Td3 = [0] * 256
    _tables_initialized = False

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

    @classmethod
    def init_tables(cls):
        if cls._tables_initialized:
            return
        for i, v in enumerate(cls.S_BOX):
            cls.INV_S_BOX[v] = i
        for i in range(256):
            s = cls.INV_S_BOX[i]
            e = cls._mul(s, 0x0E)
            b = cls._mul(s, 0x0B)
            d = cls._mul(s, 0x0D)
            nine = cls._mul(s, 0x09)
            cls.Td0[i] = (e << 24) | (nine << 16) | (d << 8) | b
            cls.Td1[i] = (b << 24) | (e << 16) | (nine << 8) | d
            cls.Td2[i] = (d << 24) | (b << 16) | (e << 8) | nine
            cls.Td3[i] = (nine << 24) | (d << 16) | (b << 8) | e
        cls._tables_initialized = True

    def __init__(self, key):
        self.init_tables()
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
            w.append((self.key[4*i] << 24) | (self.key[4*i + 1] << 16) | (self.key[4*i + 2] << 8) | self.key[4*i + 3])
        for i in range(self.nk, 4 * (self.nr + 1)):
            temp = w[i - 1]
            if i % self.nk == 0:
                t_bytes = [(temp >> 24) & 0xFF, (temp >> 16) & 0xFF, (temp >> 8) & 0xFF, temp & 0xFF]
                t_rot = self._rot_word(t_bytes)
                t_sub = self._sub_word(t_rot)
                temp = (t_sub[0] << 24) | (t_sub[1] << 16) | (t_sub[2] << 8) | t_sub[3]
                temp ^= (self.RCON[i // self.nk] << 24)
            w.append(w[i - self.nk] ^ temp)
        return w

    def decrypt_cbc(self, ciphertext, iv):
        # 预先分配内存缓冲，采用 32 位整型异或运算
        len_c = len(ciphertext)
        out = bytearray(len_c)
        prev = iv
        w = self.w
        nr = self.nr
        Td0 = self.Td0
        Td1 = self.Td1
        Td2 = self.Td2
        Td3 = self.Td3
        inv_s = self.INV_S_BOX

        for offset in range(0, len_c, 16):
            s0 = (ciphertext[offset] << 24) | (ciphertext[offset+1] << 16) | (ciphertext[offset+2] << 8) | ciphertext[offset+3]
            s1 = (ciphertext[offset+4] << 24) | (ciphertext[offset+5] << 16) | (ciphertext[offset+6] << 8) | ciphertext[offset+7]
            s2 = (ciphertext[offset+8] << 24) | (ciphertext[offset+9] << 16) | (ciphertext[offset+10] << 8) | ciphertext[offset+11]
            s3 = (ciphertext[offset+12] << 24) | (ciphertext[offset+13] << 16) | (ciphertext[offset+14] << 8) | ciphertext[offset+15]

            s0 ^= w[nr * 4]
            s1 ^= w[nr * 4 + 1]
            s2 ^= w[nr * 4 + 2]
            s3 ^= w[nr * 4 + 3]

            for r in range(nr - 1, 0, -1):
                t0 = Td0[(s0 >> 24) & 0xFF] ^ Td1[(s3 >> 16) & 0xFF] ^ Td2[(s2 >> 8) & 0xFF] ^ Td3[s1 & 0xFF] ^ w[r * 4]
                t1 = Td0[(s1 >> 24) & 0xFF] ^ Td1[(s0 >> 16) & 0xFF] ^ Td2[(s3 >> 8) & 0xFF] ^ Td3[s2 & 0xFF] ^ w[r * 4 + 1]
                t2 = Td0[(s2 >> 24) & 0xFF] ^ Td1[(s1 >> 16) & 0xFF] ^ Td2[(s0 >> 8) & 0xFF] ^ Td3[s3 & 0xFF] ^ w[r * 4 + 2]
                t3 = Td0[(s3 >> 24) & 0xFF] ^ Td1[(s2 >> 16) & 0xFF] ^ Td2[(s1 >> 8) & 0xFF] ^ Td3[s0 & 0xFF] ^ w[r * 4 + 3]
                s0, s1, s2, s3 = t0, t1, t2, t3

            b0 = (inv_s[(s0 >> 24) & 0xFF] << 24) | (inv_s[(s3 >> 16) & 0xFF] << 16) | (inv_s[(s2 >> 8) & 0xFF] << 8) | inv_s[s1 & 0xFF]
            b1 = (inv_s[(s1 >> 24) & 0xFF] << 24) | (inv_s[(s0 >> 16) & 0xFF] << 16) | (inv_s[(s3 >> 8) & 0xFF] << 8) | inv_s[s2 & 0xFF]
            b2 = (inv_s[(s2 >> 24) & 0xFF] << 24) | (inv_s[(s1 >> 16) & 0xFF] << 16) | (inv_s[(s0 >> 8) & 0xFF] << 8) | inv_s[s3 & 0xFF]
            b3 = (inv_s[(s3 >> 24) & 0xFF] << 24) | (inv_s[(s2 >> 16) & 0xFF] << 16) | (inv_s[(s1 >> 8) & 0xFF] << 8) | inv_s[s0 & 0xFF]

            b0 ^= w[0]
            b1 ^= w[1]
            b2 ^= w[2]
            b3 ^= w[3]

            out[offset]      = ((b0 >> 24) & 0xFF) ^ prev[0]
            out[offset + 1]  = ((b0 >> 16) & 0xFF) ^ prev[1]
            out[offset + 2]  = ((b0 >> 8)  & 0xFF) ^ prev[2]
            out[offset + 3]  = (b0 & 0xFF)         ^ prev[3]

            out[offset + 4]  = ((b1 >> 24) & 0xFF) ^ prev[4]
            out[offset + 5]  = ((b1 >> 16) & 0xFF) ^ prev[5]
            out[offset + 6]  = ((b1 >> 8)  & 0xFF) ^ prev[6]
            out[offset + 7]  = (b1 & 0xFF)         ^ prev[7]

            out[offset + 8]  = ((b2 >> 24) & 0xFF) ^ prev[8]
            out[offset + 9]  = ((b2 >> 16) & 0xFF) ^ prev[9]
            out[offset + 10] = ((b2 >> 8)  & 0xFF) ^ prev[10]
            out[offset + 11] = (b2 & 0xFF)         ^ prev[11]

            out[offset + 12] = ((b3 >> 24) & 0xFF) ^ prev[12]
            out[offset + 13] = ((b3 >> 16) & 0xFF) ^ prev[13]
            out[offset + 14] = ((b3 >> 8)  & 0xFF) ^ prev[14]
            out[offset + 15] = (b3 & 0xFF)         ^ prev[15]

            prev = ciphertext[offset : offset + 16]

        pad = out[-1]
        valid_len = (len_c - pad) if (1 <= pad <= 16) else len_c
        return bytes(out[:valid_len])

class Spider(BaseSpider):

    def __init__(self):
        super(Spider, self).__init__()
        self.site_url = "https://chengguodj.com"
        self.media_key = b"f5d965df75336270"
        self.media_iv = b"97b60394abc2fbe1"
        self.pure_engine = None
        self.img_cache = {}

    def init(self, extend=""):
        pass

    def _get_ssl_ctx(self):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx

    def _decrypt_image_bytes(self, ciphertext):
        # 1. 优先使用 C 扩展 (0.005 秒秒解)
        if FAST_AES is not None:
            try:
                cipher = FAST_AES.new(self.media_key, FAST_AES.MODE_CBC, self.media_iv)
                dec = cipher.decrypt(ciphertext)
                pad = dec[-1]
                return dec[:-pad] if (1 <= pad <= 16) else dec
            except Exception:
                pass

        # 2. 查表加速 PureAES 兜底
        if not self.pure_engine:
            self.pure_engine = FastPureAES(self.media_key)
        return self.pure_engine.decrypt_cbc(ciphertext, self.media_iv)

    def _fetch(self, url, headers=None, data=None):
        req_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Referer": self.site_url + "/"
        }
        if headers:
            req_headers.update(headers)
        
        req = request.Request(url, headers=req_headers, data=data)
        ctx = self._get_ssl_ctx()
        try:
            with request.urlopen(req, context=ctx, timeout=10) as resp:
                raw = resp.read()
                encoding = resp.headers.get("Content-Encoding", "").lower()
                if "gzip" in encoding:
                    try:
                        raw = gzip.decompress(raw)
                    except Exception:
                        pass
                elif "deflate" in encoding:
                    try:
                        raw = zlib.decompress(raw)
                    except Exception:
                        pass
                charset = resp.headers.get_content_charset() or "utf-8"
                return {
                    "code": resp.getcode(),
                    "final_url": resp.geturl(),
                    "headers": dict(resp.headers),
                    "body": raw.decode(charset, errors="replace")
                }
        except error.HTTPError as e:
            return {
                "code": e.code,
                "final_url": e.geturl() if hasattr(e, "geturl") else url,
                "headers": dict(e.headers) if hasattr(e, "headers") else {},
                "body": e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else ""
            }
        except Exception as e:
            return {
                "code": -1,
                "final_url": url,
                "headers": {},
                "body": str(e)
            }

    def homeContent(self, filter):
        return {
            "class": [
                {"type_id": "yuanchuang", "type_name": "原创短剧"},
                {"type_id": "mogai", "type_name": "魔改短剧"},
                {"type_id": "manju", "type_name": "漫剧"},
                {"type_id": "zhenren", "type_name": "真人短剧"},
                {"type_id": "aiduanju", "type_name": "AI短剧"},
                {"type_id": "browse", "type_name": "片库索引"}
            ],
            "filters": {}
        }

    def homeVideoContent(self):
        return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        p = int(pg)
        cat_url = "%s/%s" % (self.site_url, tid) if p <= 1 else "%s/%s/page-%d" % (self.site_url, tid, p)

        res = self._fetch(cat_url)
        body = res.get("body", "")

        vod_list = []
        seen_ids = set()

        nuxt_m = re.search(r'<script[^>]+id=["\']__NUXT_DATA__["\'][^>]*>([\s\S]*?)</script>', body)
        if nuxt_m:
            try:
                arr = json.loads(nuxt_m.group(1).strip())
                for item in arr:
                    if isinstance(item, dict) and "title" in item and ("slug" in item or "detail_route" in item):
                        t_idx = item.get("title")
                        title = arr[t_idx] if isinstance(t_idx, int) and t_idx < len(arr) else t_idx
                        if not title or not isinstance(title, str):
                            continue

                        d_route = item.get("detail_route")
                        drama_path = arr[d_route] if isinstance(d_route, int) and d_route < len(arr) else d_route
                        if not drama_path:
                            slug_val = item.get("slug")
                            slug = arr[slug_val] if isinstance(slug_val, int) and slug_val < len(arr) else slug_val
                            if slug:
                                drama_path = "/drama/%s" % slug

                        if not drama_path or drama_path in seen_ids:
                            continue

                        final_pic = ""
                        cover_obj = item.get("cover")
                        if isinstance(cover_obj, int) and cover_obj < len(arr):
                            cover_obj = arr[cover_obj]

                        if isinstance(cover_obj, dict):
                            u_idx = cover_obj.get("url")
                            raw_u = arr[u_idx] if isinstance(u_idx, int) and u_idx < len(arr) else u_idx
                            if raw_u and isinstance(raw_u, str):
                                final_pic = "http://127.0.0.1:9978/proxy?do=live&type=img&url=%s" % parse.quote(raw_u)

                        eps_val = item.get("total_episode_count") or item.get("published_episode_count") or item.get("latest_episode_number")
                        if isinstance(eps_val, int) and eps_val < len(arr) and not isinstance(arr[eps_val], (dict, list)):
                            eps_num = arr[eps_val]
                        else:
                            eps_num = eps_val
                        remarks = "ZakaTV · %s集" % eps_num if eps_num else "ZakaTV"

                        seen_ids.add(drama_path)
                        vod_list.append({
                            "vod_id": drama_path,
                            "vod_name": title,
                            "vod_pic": final_pic,
                            "vod_remarks": remarks,
                            "vod_actor": "📺TG群: https://t.me/+3t5XRPPo9mlkZDRl",
                            "vod_director": "ZakaTV"
                        })
            except Exception:
                pass

        return {
            "page": p,
            "pagecount": p + 1 if len(vod_list) >= 12 else p,
            "limit": len(vod_list),
            "total": 999,
            "list": vod_list
        }

    def detailContent(self, ids):
        drama_id = ids[0]
        detail_url = parse.urljoin(self.site_url, drama_id) if not drama_id.startswith("http") else drama_id

        res = self._fetch(detail_url)
        body = res.get("body", "")

        vod_name = ""
        title_m = re.search(r'<title>([^<]+)</title>', body, re.IGNORECASE)
        if title_m:
            vod_name = title_m.group(1).split("-")[0].replace("在线观看", "").strip()

        pic = ""
        wlw_m = re.search(r'["\'](https?://[^"\']*wlwvch\.cn[^"\']+)["\']', body)
        if wlw_m:
            pic = "http://127.0.0.1:9978/proxy?do=live&type=img&url=%s" % parse.quote(wlw_m.group(1).replace("\\u002F", "/").replace("\\/", "/"))

        desc = ""
        desc_m = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']', body, re.IGNORECASE)
        if desc_m:
            desc = desc_m.group(1).strip()

        content_str = "【📺ZakaTV·官方交流群 https://t.me/+3t5XRPPo9mlkZDRl】\n\n%s" % (desc if desc else "暂无简介")

        slug = drama_id.strip("/").split("/")[-1]

        episodes = []
        nuxt_m = re.search(r'<script[^>]+id=["\']__NUXT_DATA__["\'][^>]*>([\s\S]*?)</script>', body)
        if nuxt_m:
            try:
                arr = json.loads(nuxt_m.group(1).strip())
                for item in arr:
                    if isinstance(item, dict) and "total_episode_count" in item:
                        tot = item.get("total_episode_count")
                        tot_num = arr[tot] if isinstance(tot, int) and tot < len(arr) else tot
                        if isinstance(tot_num, int) and tot_num > 0:
                            for ep_i in range(1, tot_num + 1):
                                episodes.append("第%d集$/play/%s/%d" % (ep_i, slug, ep_i))
                            break
            except Exception:
                pass

        if not episodes:
            play_links = re.findall(r'href=["\'](/play/[^"\']+)["\']', body, re.IGNORECASE)
            seen_eps = set()
            for p_link in play_links:
                p_link = p_link.strip()
                if p_link in seen_eps:
                    continue
                seen_eps.add(p_link)
                ep_num = p_link.split("/")[-1]
                ep_title = "第%s集" % ep_num if ep_num.isdigit() else ep_num
                episodes.append("%s$%s" % (ep_title, p_link))

        if not episodes:
            total_m = re.search(r'(\d+)[\s]*(?:集|话|部)', body)
            max_ep = int(total_m.group(1)) if total_m else 1
            for i in range(1, max_ep + 1):
                episodes.append("第%d集$/play/%s/%d" % (i, slug, i))

        vod = {
            "vod_id": drama_id,
            "vod_name": vod_name if vod_name else "短剧详情",
            "vod_pic": pic,
            "vod_type": "短剧",
            "vod_year": "2026",
            "vod_area": "大陆",
            "vod_remarks": "ZakaTV · %d集" % len(episodes),
            "vod_actor": "📺TG群: https://t.me/+3t5XRPPo9mlkZDRl",
            "vod_director": "📺ZakaTV",
            "vod_content": content_str,
            "vod_play_from": "橙果短剧",
            "vod_play_url": "#".join(episodes)
        }

        return {"list": [vod]}

    def playerContent(self, flag, id, vipFlags):
        play_path = id if id.startswith("/") else "/" + id
        play_url = parse.urljoin(self.site_url, play_path)

        res = self._fetch(play_url)
        body = res.get("body", "")

        video_url = ""

        nuxt_m = re.search(r'<script[^>]+id=["\']__NUXT_DATA__["\'][^>]*>([\s\S]*?)</script>', body)
        if nuxt_m:
            try:
                arr = json.loads(nuxt_m.group(1).strip())
                for item in arr:
                    if isinstance(item, str) and ".m3u8" in item and item.startswith("http"):
                        video_url = item
                        break
            except Exception:
                pass

        if not video_url:
            m3u8_m = re.search(r'["\'](https?://[^"\'\s<>\\]+\.m3u8[^"\'\s<>\\]*)["\']', body)
            if m3u8_m:
                video_url = m3u8_m.group(1).replace("\\u002F", "/").replace("\\/", "/")

        if video_url:
            return {
                "parse": 0,
                "playUrl": "",
                "url": video_url,
                "header": {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Referer": self.site_url + "/"
                }
            }

        return {"parse": 0, "playUrl": "", "url": ""}

    def searchContent(self, key, quick, pg="1"):
        p = int(pg)
        search_url = "%s/search?keyword=%s" % (self.site_url, parse.quote(key)) if p <= 1 else "%s/search?keyword=%s&page=%d" % (self.site_url, parse.quote(key), p)

        res = self._fetch(search_url)
        body = res.get("body", "")

        vod_list = []
        seen_ids = set()

        nuxt_m = re.search(r'<script[^>]+id=["\']__NUXT_DATA__["\'][^>]*>([\s\S]*?)</script>', body)
        if nuxt_m:
            try:
                arr = json.loads(nuxt_m.group(1).strip())
                for item in arr:
                    if isinstance(item, dict) and "title" in item and ("slug" in item or "detail_route" in item):
                        t_idx = item.get("title")
                        title = arr[t_idx] if isinstance(t_idx, int) and t_idx < len(arr) else t_idx
                        if not title or not isinstance(title, str):
                            continue

                        d_route = item.get("detail_route")
                        drama_path = arr[d_route] if isinstance(d_route, int) and d_route < len(arr) else d_route
                        if not drama_path:
                            slug_val = item.get("slug")
                            slug = arr[slug_val] if isinstance(slug_val, int) and slug_val < len(arr) else slug_val
                            if slug:
                                drama_path = "/drama/%s" % slug

                        if not drama_path or drama_path in seen_ids:
                            continue

                        final_pic = ""
                        cover_obj = item.get("cover")
                        if isinstance(cover_obj, int) and cover_obj < len(arr):
                            cover_obj = arr[cover_obj]

                        if isinstance(cover_obj, dict):
                            u_idx = cover_obj.get("url")
                            raw_u = arr[u_idx] if isinstance(u_idx, int) and u_idx < len(arr) else u_idx
                            if raw_u and isinstance(raw_u, str):
                                final_pic = "http://127.0.0.1:9978/proxy?do=live&type=img&url=%s" % parse.quote(raw_u)

                        eps_val = item.get("total_episode_count") or item.get("published_episode_count") or item.get("latest_episode_number")
                        if isinstance(eps_val, int) and eps_val < len(arr) and not isinstance(arr[eps_val], (dict, list)):
                            eps_num = arr[eps_val]
                        else:
                            eps_num = eps_val
                        remarks = "ZakaTV · %s集" % eps_num if eps_num else "ZakaTV"

                        seen_ids.add(drama_path)
                        vod_list.append({
                            "vod_id": drama_path,
                            "vod_name": title,
                            "vod_pic": final_pic,
                            "vod_remarks": remarks,
                            "vod_actor": "📺TG群: https://t.me/+3t5XRPPo9mlkZDRl",
                            "vod_director": "📺ZakaTV"
                        })
            except Exception:
                pass

        return {
            "page": p,
            "pagecount": p + 1 if len(vod_list) >= 12 else p,
            "limit": len(vod_list),
            "total": 999,
            "list": vod_list
        }

    def action(self, action):
        return {}

    def liveContent(self):
        return ""

    def localProxy(self, params):
        p_type = params.get("type", "")
        if p_type == "img":
            target_url = params.get("url", "")
            if target_url:
                # 命中内存缓存直接 0ms 返回
                if target_url in self.img_cache:
                    return [200, "image/jpeg", self.img_cache[target_url]]
                try:
                    req = request.Request(target_url, headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                        "Referer": self.site_url + "/"
                    })
                    with request.urlopen(req, context=self._get_ssl_ctx(), timeout=6) as resp:
                        enc_bytes = resp.read()

                    if len(enc_bytes) % 16 == 0 and len(enc_bytes) > 0:
                        dec_bytes = self._decrypt_image_bytes(enc_bytes)
                        # 控制缓存池不超过 50 张，防止占用内存
                        if len(self.img_cache) > 50:
                            self.img_cache.clear()
                        self.img_cache[target_url] = dec_bytes
                        return [200, "image/jpeg", dec_bytes]
                    else:
                        return [200, "image/jpeg", enc_bytes]
                except Exception:
                    pass
        return [404, "text/plain", b""]

    def manualVideoCheck(self):
        return False

    def isVideoFormat(self, url):
        return False

    def destroy(self):
        if hasattr(self, "img_cache"):
            self.img_cache.clear()
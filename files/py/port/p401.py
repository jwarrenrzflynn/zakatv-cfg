import sys
import os
import re
import json
import base64
import ssl
import urllib.request
import urllib.parse
import http.cookiejar
import gzip
import zlib

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        def getCache(self, key):
            return None
        def setCache(self, key, value):
            return "fail"
        def delCache(self, key):
            return "fail"

class Spider(BaseSpider):
    def __init__(self):
        super(Spider, self).__init__()
        self.navUrls = ["https://x99dh.cc", "https://x99dh.one"]
        self.defaultHost = "https://591av.ws"
        self.siteUrl = self.defaultHost
        self.siteName = "亚洲素人精选"
        self.entryPath = "/enter"
        self.cacheKey = "ppp_porn_dynamic_site_url"
        self.mirrorPool = [
            "https://591av.ws",
            "https://591av.net",
            "https://ppp.porn"
        ]
        self._ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        self.options = {}

        self.ctx = ssl.create_default_context()
        self.ctx.check_hostname = False
        self.ctx.verify_mode = ssl.CERT_NONE
        try:
            self.ctx.set_ciphers("DEFAULT@SECLEVEL=1")
        except Exception:
            pass

        self.cj = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cj),
            urllib.request.HTTPSHandler(context=self.ctx)
        )

    def init(self, extend=""):
        if isinstance(extend, dict):
            self.options = extend
        elif extend:
            try:
                self.options = json.loads(extend)
            except Exception:
                self.options = {}

        cached_site = self.getCache(self.cacheKey)
        if cached_site and str(cached_site).startswith("http"):
            self.siteUrl = str(cached_site).strip().rstrip("/")
        else:
            self._refresh_site_url()
        return True

    def getName(self):
        return "591AV·动态保活版"

    def isVideoFormat(self, url):
        low = (url or "").lower()
        return any(k in low for k in (".m3u8", ".mp4", ".flv", ".mkv", ".ts", ".mpd"))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        self.options = {}

    def localProxy(self, params):
        return [404, "text/plain; charset=utf-8", "Proxy not configured"]

    def _check_host_alive(self, base_url):
        target = "%s%s" % (base_url.rstrip("/"), self.entryPath)
        res = self._fetch(target, check_host=False)
        return res.get("code") in (200, 301, 302)

    def _refresh_site_url(self):
        headers = {
            "User-Agent": self._ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate"
        }

        for nav in self.navUrls:
            text = ""
            try:
                req = urllib.request.Request(nav, headers=headers)
                with self.opener.open(req, timeout=8) as resp:
                    raw = resp.read()
                    enc = getattr(resp, "headers", {}).get("Content-Encoding", "")
                    if raw.startswith(b"\x1f\x8b") or enc == "gzip":
                        raw = gzip.decompress(raw)
                    text = raw.decode("utf-8", errors="ignore")
            except urllib.error.HTTPError as e:
                try:
                    raw = e.read()
                    if raw.startswith(b"\x1f\x8b"):
                        raw = gzip.decompress(raw)
                    text = raw.decode("utf-8", errors="ignore")
                except Exception:
                    text = ""
            except Exception:
                continue

            if not text:
                continue

            b64_blocks = re.findall(r'["\']([A-Za-z0-9+/=]{100,})["\']', text)
            for b in b64_blocks:
                try:
                    decoded = base64.b64decode(b).decode("utf-8", errors="ignore")
                    unquoted = urllib.parse.unquote(decoded)
                    if "[" in unquoted and (self.siteName in unquoted or "591av" in unquoted.lower() or "ppp.porn" in unquoted.lower()):
                        site_list = json.loads(unquoted)
                        for item in site_list:
                            name = item.get("name", "").strip()
                            if self.siteName in name or "591av" in name.lower():
                                cand_urls = []
                                main_url = item.get("url", "")
                                if main_url:
                                    cand_urls.append(main_url)
                                for u_obj in item.get("urls", []):
                                    u = u_obj.get("url", "")
                                    if u and u not in cand_urls:
                                        cand_urls.append(u)

                                for c_url in cand_urls:
                                    parsed = urllib.parse.urlparse(c_url)
                                    base = "%s://%s" % (parsed.scheme, parsed.netloc)
                                    if self._check_host_alive(base):
                                        self.siteUrl = base
                                        self.setCache(self.cacheKey, base)
                                        return True
                except Exception:
                    continue

        for fallback in self.mirrorPool:
            if self._check_host_alive(fallback):
                self.siteUrl = fallback
                self.setCache(self.cacheKey, fallback)
                return True

        return False

    def _fetch(self, target_url, referer="", check_host=True):
        if not target_url:
            return {"code": 0, "text": "", "err": "", "final_url": ""}
        if target_url.startswith("//"):
            target_url = "https:" + target_url
        elif target_url.startswith("/"):
            target_url = self.siteUrl + target_url

        headers = {
            "User-Agent": self._ua,
            "Referer": referer if referer else (self.siteUrl + self.entryPath),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive"
        }

        last_err = ""
        domain_retried = False

        for attempt in range(2):
            try:
                req = urllib.request.Request(target_url, headers=headers)
                with self.opener.open(req, timeout=10) as resp:
                    code = resp.getcode()
                    final_url = resp.geturl()
                    raw = resp.read()
                    enc = getattr(resp, "headers", {}).get("Content-Encoding", "")
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
                    return {"code": code, "text": text, "err": "", "final_url": final_url}
            except urllib.error.HTTPError as e:
                last_err = "HTTP %s" % e.code
                if e.code in (404, 451, 500, 502, 503) and check_host and not domain_retried:
                    old_host = urllib.parse.urlparse(self.siteUrl).netloc
                    self.delCache(self.cacheKey)
                    if self._refresh_site_url():
                        domain_retried = True
                        new_host = urllib.parse.urlparse(self.siteUrl).netloc
                        target_url = target_url.replace(old_host, new_host)
                        continue
                if e.code in (451, 403, 429) and attempt == 0:
                    continue
                return {"code": e.code, "text": "", "err": str(e), "final_url": target_url}
            except Exception as e:
                last_err = str(e)
                if check_host and not domain_retried:
                    old_host = urllib.parse.urlparse(self.siteUrl).netloc
                    self.delCache(self.cacheKey)
                    if self._refresh_site_url():
                        domain_retried = True
                        new_host = urllib.parse.urlparse(self.siteUrl).netloc
                        target_url = target_url.replace(old_host, new_host)
                        continue
                if attempt == 0:
                    continue
                return {"code": -1, "text": "", "err": str(e), "final_url": target_url}

        return {"code": -1, "text": "", "err": last_err, "final_url": target_url}

    def homeContent(self, filter):
        classes = [
            {"type_id": "china-av", "type_name": "中国AV"},
            {"type_id": "japan-producer", "type_name": "日本片商"},
            {"type_id": "amateur", "type_name": "素人自拍"},
            {"type_id": "china", "type_name": "中国"},
            {"type_id": "taiwan", "type_name": "台湾"},
            {"type_id": "japan", "type_name": "日本"},
            {"type_id": "se-asia", "type_name": "东南亚"},
            {"type_id": "korea", "type_name": "韩国"},
            {"type_id": "hongkong", "type_name": "香港"},
            {"type_id": "cosplay", "type_name": "Cosplay"},
            {"type_id": "streamer", "type_name": "主播"},
            {"type_id": "first-person-pov", "type_name": "主观视角"},
            {"type_id": "bdsm", "type_name": "凌辱"},
            {"type_id": "drama", "type_name": "剧情"},
            {"type_id": "threesome", "type_name": "多P"},
            {"type_id": "91-tanhua", "type_name": "探花"},
            {"type_id": "released", "type_name": "流出"},
            {"type_id": "uncensored", "type_name": "无码"},
            {"type_id": "lesbian", "type_name": "百合"},
            {"type_id": "exhibitionists", "type_name": "野外露出"},
            {"type_id": "office-lady", "type_name": "OL"},
            {"type_id": "acg", "type_name": "动漫"},
            {"type_id": "costume", "type_name": "古装"},
            {"type_id": "maid", "type_name": "女仆"},
            {"type_id": "student", "type_name": "学生"},
            {"type_id": "cheongsam", "type_name": "旗袍"},
            {"type_id": "kemonomimi", "type_name": "兽耳"},
            {"type_id": "yoga-pants", "type_name": "瑜伽裤"},
            {"type_id": "dolfin-shorts", "type_name": "真理裤"},
            {"type_id": "flight-attendant", "type_name": "空姐"},
            {"type_id": "pantyhose", "type_name": "丝袜"},
            {"type_id": "nurse", "type_name": "护士"},
            {"type_id": "knee-socks", "type_name": "过膝袜"}
        ]

        sort_filter = {
            "key": "sort",
            "name": "排序",
            "value": [
                {"n": "新上架", "v": "post_date"},
                {"n": "收藏量", "v": "most_favourited"},
                {"n": "观看次数(本月)", "v": "month_views"},
                {"n": "观看次数(总计)", "v": "video_viewed"}
            ]
        }

        filters = {}
        for c in classes:
            filters[c["type_id"]] = [sort_filter]

        return {
            "class": classes,
            "filters": filters,
            "list": []
        }

    def homeVideoContent(self):
        return {"list": []}

    def _parse_video_cards(self, html_body):
        blocks = re.split(r'(?=<a[^>]+href=[\'"][^\'"]*?/v/[a-zA-Z0-9_\-]+/?)', html_body)
        parsed_items = []
        seen_ids = set()

        for blk in blocks[1:]:
            v_match = re.search(r'href=[\'"]([^\'"]*?/v/([a-zA-Z0-9_\-]+)/?)[\'"]', blk)
            if not v_match:
                continue
            vod_id = v_match.group(2).strip()
            if vod_id in seen_ids:
                continue

            card_chunk = blk[:1200]

            img_match = re.search(r'data-src=[\'"]([^\'"]+)[\'"]', card_chunk, re.I)
            vod_pic = img_match.group(1).strip() if img_match else ""
            if not vod_pic:
                alt_img = re.search(r'(?:data-original|data-poster|src)=[\'"]([^\'"]+)[\'"]', card_chunk, re.I)
                if alt_img and not any(kw in alt_img.group(1).lower() for kw in ["placeholder", "logo.png"]):
                    vod_pic = alt_img.group(1).strip()

            if vod_pic.startswith("//"):
                vod_pic = "https:" + vod_pic
            elif vod_pic.startswith("/"):
                vod_pic = self.siteUrl + vod_pic

            title_match = re.search(r'alt=[\'"]([^\'"]+)[\'"]', card_chunk, re.I)
            if not title_match:
                title_match = re.search(r'title=[\'"]([^\'"]+)[\'"]', card_chunk, re.I)
            if title_match:
                vod_name = title_match.group(1).strip()
            else:
                text_match = re.search(r'<a[^>]+href=[\'"][^\'"]*?/v/[^\'"]+[\'"][^>]*>(.*?)</a>', card_chunk, re.S | re.I)
                clean_text = re.sub(r'<[^>]+>', '', text_match.group(1)).strip() if text_match else ""
                vod_name = clean_text or vod_id

            dur_match = re.search(r'class=[\'"][^\'"]*?duration[^\'"]*?[\'"][^>]*>([0-9:]+)<', card_chunk, re.I)
            if not dur_match:
                dur_match = re.search(r'>\s*([0-9]{1,2}:[0-9]{2}(?::[0-9]{2})?)\s*<', card_chunk)
            duration = dur_match.group(1).strip() if dur_match else ""
            vod_remarks = ("ZakaTV | %s" % duration) if duration else "ZakaTV"

            seen_ids.add(vod_id)
            parsed_items.append({
                "vod_id": vod_id,
                "vod_name": vod_name,
                "vod_pic": vod_pic,
                "vod_remarks": vod_remarks,
                "vod_actor": "📺TG群: https://t.me/+3t5XRPPo9mlkZDRl",
                "vod_director": "📺ZakaTV",
                "style": {
                    "type": "rect",
                    "ratio": 1.78
                }
            })
        return parsed_items

    def categoryContent(self, tid, pg, filter, extend):
        page_num = int(pg) if str(pg).isdigit() else 1
        sort_by = ""
        if extend and isinstance(extend, dict):
            sort_by = extend.get("sort", "")

        path_parts = ["categories", tid]
        if sort_by and sort_by != "post_date":
            path_parts.append(sort_by)
        if page_num > 1:
            path_parts.append(str(page_num))

        req_path = "/%s/" % "/".join(path_parts)
        resp = self._fetch(req_path)
        parsed_items = self._parse_video_cards(resp.get("text", ""))

        if not parsed_items and sort_by and sort_by != "post_date":
            if page_num > 1:
                alt_path = "/categories/%s/%d/?sort_by=%s" % (tid, page_num, sort_by)
            else:
                alt_path = "/categories/%s/?sort_by=%s" % (tid, sort_by)
            alt_resp = self._fetch(alt_path)
            parsed_items = self._parse_video_cards(alt_resp.get("text", ""))

        return {
            "page": page_num,
            "pagecount": 999,
            "limit": len(parsed_items) if parsed_items else 20,
            "total": 9999,
            "list": parsed_items
        }

    def detailContent(self, ids):
        vod_id = ids[0] if isinstance(ids, list) and ids else str(ids)
        target_path = "/v/%s/" % vod_id
        resp = self._fetch(target_path)
        html_body = resp.get("text", "")

        title_m = re.search(r'<h1[^>]*>(.*?)</h1>', html_body, re.S | re.I)
        vod_name = re.sub(r'<[^>]+>', '', title_m.group(1)).strip() if title_m else vod_id

        pic_m = re.search(r'property=[\'"]og:image[\'"]\s+content=[\'"]([^\'"]+)[\'"]', html_body, re.I)
        if not pic_m:
            pic_m = re.search(r'poster=[\'"]([^\'"]+)[\'"]', html_body, re.I)
        vod_pic = pic_m.group(1).strip() if pic_m else ""
        if vod_pic.startswith("//"):
            vod_pic = "https:" + vod_pic
        elif vod_pic.startswith("/"):
            vod_pic = self.siteUrl + vod_pic

        desc_prefix = "📺ZakaTV独家收录 | 官方交流群: https://t.me/+3t5XRPPo9mlkZDRl\n"
        desc_m = re.search(r'property=[\'"]og:description[\'"]\s+content=[\'"]([^\'"]+)[\'"]', html_body, re.I)
        raw_desc = desc_m.group(1).strip() if desc_m else ""
        vod_content = desc_prefix + (raw_desc or "精选高清成人影视")

        vod_detail = {
            "vod_id": vod_id,
            "vod_name": vod_name,
            "vod_pic": vod_pic,
            "type_name": "高清专区",
            "vod_year": "",
            "vod_area": "亚洲",
            "vod_remarks": "ZakaTV",
            "vod_actor": "📺TG群: https://t.me/+3t5XRPPo9mlkZDRl",
            "vod_director": "📺ZakaTV",
            "vod_content": vod_content,
            "vod_play_from": "Zaka专线",
            "vod_play_url": "正片$%s" % vod_id
        }

        return {"list": [vod_detail]}

    def playerContent(self, flag, id, vipFlags):
        vod_id = str(id).strip()
        detail_path = "/v/%s/" % vod_id
        resp = self._fetch(detail_path)
        html_body = resp.get("text", "")

        stream_match = re.search(r"var\s+stream\s*=\s*['\"]([^'\"]+\.m3u8[^'\"]*)['\"]", html_body, re.I)
        video_url = stream_match.group(1).strip() if stream_match else ""

        if not video_url:
            gen_match = re.search(r"['\"](https?://[^'\"]+?/stream/[^'\"]+?\.m3u8[^'\"]*)['\"]", html_body, re.I)
            if gen_match:
                video_url = gen_match.group(1).strip()

        headers = {
            "User-Agent": self._ua,
            "Referer": self.siteUrl + detail_path
        }

        return {
            "parse": 0,
            "url": video_url,
            "header": headers
        }

    def searchContent(self, key, quick, pg="1"):
        page_num = int(pg) if str(pg).isdigit() else 1
        encoded_key = urllib.parse.quote(key)
        if page_num > 1:
            req_path = "/search/%s/%d/" % (encoded_key, page_num)
        else:
            req_path = "/search/%s/" % encoded_key

        resp = self._fetch(req_path)
        parsed_items = self._parse_video_cards(resp.get("text", ""))

        return {
            "page": page_num,
            "pagecount": 999,
            "limit": len(parsed_items) if parsed_items else 20,
            "total": 9999,
            "list": parsed_items
        }

    def liveContent(self):
        return ""

    def action(self, action):
        if action == "toast":
            return {"msg": "当前有效发布域: %s" % self.siteUrl}
        return {"msg": "ok"}

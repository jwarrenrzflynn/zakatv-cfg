import sys
import os
import re
import json
import base64
import html as html_lib
import urllib.request
import urllib.parse
from http.cookiejar import CookieJar
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

class Spider(SpiderBase):
    def __init__(self):
        super(Spider, self).__init__()
        self.navUrls = ["https://x99dh.cc", "https://x99dh.one"]
        self.defaultHost = "https://xanimu.one"
        self.siteUrl = self.defaultHost
        self.siteName = "Xanimu"
        self.entryPath = "/zh-CN/"
        self.cacheKey = "xanimu_dynamic_site_url"
        self.mirrorPool = [
            "https://xanimu.one",
            "https://xanimu.net",
            "https://xanimu.tv"
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

        self.cookie_jar = CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookie_jar),
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
        return "XAnimu·动态发布自愈版"

    def isVideoFormat(self, url):
        low = (url or "").lower()
        return any(k in low for k in (".m3u8", ".mp4", ".flv", ".mkv", ".ts", ".mpd"))

    def manualVideoCheck(self):
        return False

    def _safe_quote_url(self, raw_url):
        parts = urllib.parse.urlsplit(raw_url)
        path = urllib.parse.quote(urllib.parse.unquote(parts.path))
        query = urllib.parse.quote(urllib.parse.unquote(parts.query), safe="=&?+")
        return urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, query, parts.fragment))

    def _check_host_alive(self, base_url):
        target = "%s%s" % (base_url.rstrip("/"), self.entryPath)
        res = self._fetch(target, check_host=False)
        return res.get("code") == 200

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
                    if "[" in unquoted and (self.siteName.lower() in unquoted.lower()):
                        site_list = json.loads(unquoted)
                        for item in site_list:
                            name = item.get("name", "").strip()
                            if self.siteName.lower() in name.lower():
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
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive"
        }

        last_err = ""
        domain_retried = False

        for attempt in range(2):
            try:
                safe_url = self._safe_quote_url(target_url)
                req = urllib.request.Request(safe_url, headers=headers)
                with self.opener.open(req, timeout=12) as resp:
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
            {"type_id": "/zh-CN/36900-2d/", "type_name": "2D"},
            {"type_id": "/zh-CN/5-3d-无尽/", "type_name": "3D"},
            {"type_id": "/zh-CN/17-ahegao-无尽/", "type_name": "Ahegao"},
            {"type_id": "/zh-CN/生成了-61627-个人工智能/", "type_name": "AI色情"},
            {"type_id": "/zh-CN/47418外星人/", "type_name": "外侨"},
            {"type_id": "SUB_CAT", "type_name": "📁 分类"},
            {"type_id": "SUB_ACTOR", "type_name": "👤 人物"},
            {"type_id": "SUB_TAG", "type_name": "🏷️ 标签"}
        ]
        return {
            "class": classes,
            "filters": {}
        }

    def homeVideoContent(self):
        return {"list": []}

    def _extract_video_cards(self, html_text):
        vod_list = []
        seen_ids = set()
        blocks = re.findall(r'<div[^>]*class=["\'][^"\']*video-block[^"\']*["\'][^>]*>([\s\S]*?)</div>\s*</div>', html_text, re.I)

        for b in blocks:
            m_href = re.search(r'href=["\']([^"\']+)["\']', b)
            m_img = re.search(r'(?:data-src|src)=["\']([^"\']+)["\']', b)
            m_t = re.search(r'title=["\']([^"\']+)["\']', b) or re.search(r'<span[^>]*class=["\']title[^"\']*["\'][^>]*>(.*?)</span>', b)
            m_dur = re.search(r'class=["\'][^"\']*(?:duration|time)[^"\']*["\'][^>]*>(.*?)<', b)

            if m_href and (m_img or m_t):
                raw_href = m_href.group(1).strip()
                parsed_path = urllib.parse.urlsplit(raw_href).path
                if not parsed_path.startswith("/zh-CN/") or any(bad in parsed_path for bad in ["/类别/", "/4875-", "/行李牌/"]):
                    continue
                if parsed_path in seen_ids or parsed_path in ["/zh-CN/", "/zh-CN"]:
                    continue

                vod_pic = m_img.group(1).strip() if m_img else ""
                if "flags" in vod_pic.lower() or "logo" in vod_pic.lower():
                    vod_pic = "https://img.icons8.com/color/480/anime.png"
                elif vod_pic.startswith("//"):
                    vod_pic = "https:" + vod_pic
                elif vod_pic.startswith("/"):
                    vod_pic = self.siteUrl + vod_pic

                raw_title = m_t.group(1).strip() if m_t else ""
                if not raw_title:
                    m_slug = re.search(r'/zh-CN/\d+-([^/]+)/?', parsed_path)
                    if m_slug:
                        raw_title = urllib.parse.unquote(m_slug.group(1)).replace("-", " ")
                raw_title = re.sub(r'<[^>]+>', '', raw_title).strip()
                raw_title = html_lib.unescape(raw_title)

                raw_duration = m_dur.group(1).strip() if m_dur else ""
                vod_remarks = ("📺ZakaTV | %s" % raw_duration) if raw_duration else "📺ZakaTV"

                if raw_title and len(raw_title) > 1:
                    seen_ids.add(parsed_path)
                    vod_list.append({
                        "vod_id": parsed_path,
                        "vod_name": raw_title,
                        "vod_pic": vod_pic,
                        "vod_remarks": vod_remarks
                    })

        return vod_list

    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg) if pg and str(pg).isdigit() else 1
        vod_list = []

        if tid == "SUB_CAT":
            cat_path = "/zh-CN/%s/" % urllib.parse.quote("类别")
            req_url = ("%s%spage/%d/" % (self.siteUrl, cat_path, page)) if page > 1 else ("%s%s" % (self.siteUrl, cat_path))
            res = self._fetch(req_url)
            html_text = res.get("text", "")
            cat_blocks = re.findall(r'<div[^>]*class=["\'][^"\']*video-block-cat[^"\']*["\'][^>]*>([\s\S]*?)</div>\s*</div>', html_text, re.I)

            seen_ids = set()
            for cb in cat_blocks:
                m_href = re.search(r'href=["\']([^"\']+)["\']', cb)
                m_img = re.search(r'(?:data-src|src)=["\']([^"\']+)["\']', cb)
                m_t = re.search(r'title=["\']([^"\']+)["\']', cb) or re.search(r'<span[^>]*class=["\']title[^"\']*["\'][^>]*>(.*?)</span>', cb)
                m_cnt = re.search(r'<div[^>]*class=["\']video-datas-category-count[^"\']*["\'][^>]*>(.*?)</div>', cb)

                if m_href and m_t:
                    raw_href = m_href.group(1).strip()
                    parsed_path = urllib.parse.urlsplit(raw_href).path
                    if parsed_path in seen_ids:
                        continue
                    seen_ids.add(parsed_path)

                    pic = m_img.group(1).strip() if m_img else ""
                    if pic.startswith("//"):
                        pic = "https:" + pic
                    elif pic.startswith("/"):
                        pic = self.siteUrl + pic

                    title = html_lib.unescape(m_t.group(1).strip())
                    count_str = re.sub(r'<[^>]+>', '', m_cnt.group(1)).strip() if m_cnt else ""
                    remarks = "📁 %s" % count_str if count_str else "📁 分类"

                    vod_list.append({
                        "vod_id": parsed_path,
                        "vod_name": title,
                        "vod_pic": pic,
                        "vod_remarks": remarks,
                        "vod_tag": "folder"
                    })

        elif tid == "SUB_ACTOR":
            actor_path = "/zh-CN/%s/" % urllib.parse.quote("4875-视频演员")
            req_url = ("%s%spage/%d/" % (self.siteUrl, actor_path, page)) if page > 1 else ("%s%s" % (self.siteUrl, actor_path))
            res = self._fetch(req_url)
            html_text = res.get("text", "")
            act_blocks = re.findall(r'<div[^>]*class=["\'][^"\']*video-block-cat[^"\']*["\'][^>]*>([\s\S]*?)</div>\s*</div>', html_text, re.I)

            seen_ids = set()
            for ab in act_blocks:
                m_href = re.search(r'href=["\']([^"\']+)["\']', ab)
                m_img = re.search(r'(?:data-src|src)=["\']([^"\']+)["\']', ab)
                m_t = re.search(r'title=["\']([^"\']+)["\']', ab) or re.search(r'<span[^>]*class=["\']title[^"\']*["\'][^>]*>(.*?)</span>', ab)
                m_cnt = re.search(r'<div[^>]*class=["\']video-datas-category-count[^"\']*["\'][^>]*>(.*?)</div>', ab)

                if m_href and m_t:
                    raw_href = m_href.group(1).strip()
                    parsed = urllib.parse.urlsplit(raw_href)
                    final_param = parsed.path + ("?" + parsed.query if parsed.query else "")
                    if final_param in seen_ids:
                        continue
                    seen_ids.add(final_param)

                    pic = m_img.group(1).strip() if m_img else ""
                    if pic.startswith("//"):
                        pic = "https:" + pic
                    elif pic.startswith("/"):
                        pic = self.siteUrl + pic

                    title = html_lib.unescape(m_t.group(1).strip())
                    count_str = re.sub(r'<[^>]+>', '', m_cnt.group(1)).strip() if m_cnt else ""
                    remarks = "👤 %s" % count_str if count_str else "👤 人物"

                    vod_list.append({
                        "vod_id": final_param,
                        "vod_name": title,
                        "vod_pic": pic,
                        "vod_remarks": remarks,
                        "vod_tag": "folder"
                    })

        elif tid == "SUB_TAG":
            res = self._fetch(self.siteUrl + self.entryPath)
            html_text = res.get("text", "")
            seen_tags = set()

            all_tag_links = re.findall(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>([\s\S]*?)</a>', html_text)
            for h, inner in all_tag_links:
                clean_text = re.sub(r'<[^>]+>', '', inner).strip()
                if "/zh-CN/" in h and clean_text and len(clean_text) <= 20:
                    if not any(bad in clean_text for bad in ["首页", "分类", "人物", "标签", "搜索", "登录"]):
                        parsed_path = urllib.parse.urlsplit(h).path
                        if parsed_path in seen_tags or parsed_path in ["/zh-CN/", "/zh-CN"]:
                            continue
                        seen_tags.add(parsed_path)
                        vod_list.append({
                            "vod_id": parsed_path,
                            "vod_name": html_lib.unescape(clean_text),
                            "vod_pic": "https://img.icons8.com/color/480/tags.png",
                            "vod_remarks": "🏷️ 标签",
                            "vod_tag": "folder"
                        })
                        if len(vod_list) >= 60:
                            break

        else:
            clean_tid = tid.replace("folder://", "").strip()
            if not clean_tid.startswith("/"):
                clean_tid = "/" + clean_tid

            if "?" in clean_tid:
                req_url = "%s%s&page=%d" % (self.siteUrl, clean_tid, page) if page > 1 else ("%s%s" % (self.siteUrl, clean_tid))
            else:
                if not clean_tid.endswith("/"):
                    clean_tid += "/"
                req_url = "%s%spage/%d/" % (self.siteUrl, clean_tid, page) if page > 1 else ("%s%s" % (self.siteUrl, clean_tid))

            res = self._fetch(req_url)
            html_text = res.get("text", "")
            vod_list = self._extract_video_cards(html_text)

        page_count = page + 1 if len(vod_list) >= 12 else page

        return {
            "page": page,
            "pagecount": page_count,
            "limit": len(vod_list) if vod_list else 20,
            "total": page_count * 20,
            "list": vod_list
        }

    def detailContent(self, ids):
        vod_id = ids[0] if isinstance(ids, list) else str(ids)
        clean_id = str(vod_id).strip()

        if clean_id.startswith("folder://") or any(marker in clean_id for marker in ["/36900-", "/5-3d-", "/17-ahegao-", "/生成了-", "/47418", "?actors=", "/行李牌/"]):
            target_path = clean_id.replace("folder://", "").strip()
            if not target_path.startswith("/"):
                target_path = "/" + target_path
            req_url = "%s%s" % (self.siteUrl, target_path)
            res = self._fetch(req_url)
            cards = self._extract_video_cards(res.get("text", ""))
            if cards:
                return {"list": cards}

        detail_url = "%s%s" % (self.siteUrl, clean_id) if clean_id.startswith("/") else clean_id

        try:
            res = self._fetch(detail_url)
            html_text = res.get("text", "")

            title_m = re.search(r'<title>(.*?)</title>', html_text, re.I | re.S)
            vod_name = html_lib.unescape(title_m.group(1).split("-")[0].strip()) if title_m else "动漫正片"

            pic_m = re.search(r'<meta[^>]*property=["\']og:image["\'][^>]*content=["\']([^"\']+)["\']', html_text, re.I)
            vod_pic = pic_m.group(1).strip() if pic_m else ""

            desc_m = re.search(r'<meta[^>]*property=["\']og:description["\'][^>]*content=["\']([^"\']+)["\']', html_text, re.I)
            raw_desc = html_lib.unescape(desc_m.group(1).strip()) if desc_m else ""

        except Exception:
            vod_name = "动漫正片"
            vod_pic = ""
            raw_desc = ""

        full_desc = (
            "【🔥 官方交流群: https://t.me/+3t5XRPPo9mlkZDRl】\n"
            "【当前发布域名: %s】\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "%s"
        ) % (self.siteUrl, raw_desc if raw_desc else "XAnimu 原画精选。")

        return {
            "list": [
                {
                    "vod_id": str(clean_id),
                    "vod_name": vod_name,
                    "vod_pic": vod_pic,
                    "type_name": "成人动漫",
                    "vod_year": "2026",
                    "vod_area": "日本",
                    "vod_actor": "📺TG群: https://t.me/+3t5XRPPo9mlkZDRl",
                    "vod_director": "📺ZakaTV",
                    "vod_content": full_desc.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"),
                    "vod_play_from": "📺ZakaTV",
                    "vod_play_url": "正片$%s" % str(clean_id)
                }
            ]
        }

    def playerContent(self, flag, id, vipFlags):
        clean_id = str(id).strip()
        detail_url = "%s%s" % (self.siteUrl, clean_id) if clean_id.startswith("/") else clean_id

        play_stream_url = ""
        header = {
            "User-Agent": self._ua,
            "Referer": self.siteUrl + "/"
        }

        try:
            res = self._fetch(detail_url)
            html_text = res.get("text", "")

            v_tags = re.findall(r'<video[^>]*src=["\']([^"\']+)["\']', html_text, re.I)
            if v_tags:
                play_stream_url = v_tags[0]

            if not play_stream_url:
                all_mp4 = re.findall(r'["\'](https?:[^"\']+\.mp4[^"\']*)["\']', html_text, re.I)
                clean_candidates = []
                for u in all_mp4:
                    u_clean = u.replace("\\/", "/")
                    if "trailer" not in u_clean and "preview" not in u_clean:
                        clean_candidates.append(u_clean)

                high_pool = [u for u in clean_candidates if "high" in u]
                if high_pool:
                    play_stream_url = high_pool[0]
                elif clean_candidates:
                    play_stream_url = clean_candidates[0]

        except Exception:
            play_stream_url = ""

        return {
            "parse": 0,
            "playUrl": "",
            "url": play_stream_url,
            "header": header
        }

    def searchContent(self, key, quick, pg="1"):
        if not key:
            return {"page": 1, "pagecount": 1, "limit": 0, "total": 0, "list": []}

        page = int(pg) if pg and str(pg).isdigit() else 1
        encoded_key = urllib.parse.quote(str(key).strip())

        if page > 1:
            req_url = "%s/zh-CN/page/%d/?s=%s" % (self.siteUrl, page, encoded_key)
        else:
            req_url = "%s/zh-CN/?s=%s" % (self.siteUrl, encoded_key)

        vod_list = []
        try:
            res = self._fetch(req_url)
            vod_list = self._extract_video_cards(res.get("text", ""))
        except Exception:
            vod_list = []

        return {
            "page": page,
            "pagecount": page + 1 if len(vod_list) >= 12 else page,
            "limit": len(vod_list) if vod_list else 20,
            "total": 100,
            "list": vod_list
        }

    def action(self, action):
        if action == "toast":
            return {"msg": "当前有效发布域: %s" % self.siteUrl}
        return {"msg": "ok"}

    def liveContent(self):
        return ""

    def localProxy(self, params):
        return [404, "text/plain; charset=utf-8", "Proxy not configured"]

    def destroy(self):
        self.options = {}
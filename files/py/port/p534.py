import os
import re
import ssl
import json
import gzip
import zlib
import uuid
import urllib.request
import urllib.parse
from base.spider import Spider

class Spider(Spider):
    def getName(self):
        return "XiangJiaoAI"

    def init(self, extend=""):
        self.site_url = "https://xiangjiaoai.ai"
        self.api_url = "%s/api/theater" % self.site_url
        self.publish_url = "https://xiangjiao01.com"
        self.cms_base = "https://mediacms.wtayty.cn"
        self.cached_token = ""
        self.cursor_cache = {}
        self.headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/27.0.1 Mobile/15E148 Safari/604.1",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh-Hans;q=0.9",
            "Connection": "keep-alive"
        }
        self.api_headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/27.0.1 Mobile/15E148 Safari/604.1",
            "Accept": "application/json",
            "Accept-Language": "zh-CN,zh-Hans;q=0.9",
            "Referer": "%s/theater" % self.site_url,
            "Connection": "keep-alive"
        }
        self.ssl_ctx = ssl.create_default_context()
        self.ssl_ctx.check_hostname = False
        self.ssl_ctx.verify_mode = ssl.CERT_NONE

    def _check_and_refresh_domain(self):
        code, _ = self._fetch_api(self.api_url, {"limit": 1})
        if code == 200:
            return

        try:
            req = urllib.request.Request(self.publish_url, headers=self.headers)
            with urllib.request.urlopen(req, context=self.ssl_ctx, timeout=3) as resp:
                content = resp.read()
                enc = resp.headers.get("Content-Encoding", "").lower()
                if "gzip" in enc:
                    try:
                        content = gzip.decompress(content)
                    except Exception:
                        pass
                elif "deflate" in enc:
                    try:
                        content = zlib.decompress(content)
                    except Exception:
                        pass
                html = content.decode("utf-8", errors="ignore")
                urls = re.findall(r'https?://(?:xjai\d+|ksou\d+|xiangjiao[a-zA-Z0-9]*)\.[a-zA-Z]{2,6}', html)
                for u in urls:
                    u_clean = u.rstrip("/")
                    if "xiangjiao01.com" in u_clean or u_clean == self.site_url:
                        continue
                    test_api = "%s/api/theater?limit=1" % u_clean
                    req_test = urllib.request.Request(test_api, headers=self.api_headers)
                    try:
                        with urllib.request.urlopen(req_test, context=self.ssl_ctx, timeout=3) as t_resp:
                            if t_resp.getcode() == 200:
                                self.site_url = u_clean
                                self.api_url = "%s/api/theater" % self.site_url
                                self.api_headers["Referer"] = "%s/theater" % self.site_url
                                return
                    except Exception:
                        pass
        except Exception:
            pass

    def _fetch(self, url, headers=None):
        req_headers = dict(self.headers)
        if headers:
            req_headers.update(headers)
        req = urllib.request.Request(url, headers=req_headers)
        try:
            with urllib.request.urlopen(req, context=self.ssl_ctx, timeout=8) as resp:
                code = resp.getcode()
                final_url = resp.geturl()
                resp_headers = dict(resp.headers)
                content = resp.read()
                encoding = resp_headers.get("Content-Encoding", "").lower()
                if "gzip" in encoding:
                    try:
                        content = gzip.decompress(content)
                    except Exception:
                        pass
                elif "deflate" in encoding:
                    try:
                        content = zlib.decompress(content)
                    except Exception:
                        pass
                text = content.decode("utf-8", errors="ignore")
                return code, final_url, resp_headers, text
        except Exception as e:
            return 0, url, {}, str(e)

    def _fetch_api(self, url, params=None, extra_headers=None):
        if params:
            qs = urllib.parse.urlencode(params)
            url = "%s?%s" % (url, qs)
        headers = dict(self.api_headers)
        if extra_headers:
            headers.update(extra_headers)
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, context=self.ssl_ctx, timeout=8) as resp:
                code = resp.getcode()
                content = resp.read()
                encoding = resp.headers.get("Content-Encoding", "").lower()
                if "gzip" in encoding:
                    try:
                        content = gzip.decompress(content)
                    except Exception:
                        pass
                elif "deflate" in encoding:
                    try:
                        content = zlib.decompress(content)
                    except Exception:
                        pass
                text = content.decode("utf-8", errors="ignore")
                try:
                    return code, json.loads(text)
                except Exception:
                    return code, {"raw": text}
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", errors="ignore")
            except Exception:
                pass
            return e.code, {"error": body}
        except Exception as e:
            return 0, {"exception": str(e)}

    def _post_json(self, url, payload, custom_headers=None):
        data_bytes = json.dumps(payload).encode("utf-8")
        headers = dict(self.api_headers)
        headers["Content-Type"] = "application/json"
        headers["Content-Length"] = str(len(data_bytes))
        if custom_headers:
            headers.update(custom_headers)

        req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, context=self.ssl_ctx, timeout=8) as resp:
                code = resp.getcode()
                content = resp.read()
                encoding = resp.headers.get("Content-Encoding", "").lower()
                if "gzip" in encoding:
                    try:
                        content = gzip.decompress(content)
                    except Exception:
                        pass
                elif "deflate" in encoding:
                    try:
                        content = zlib.decompress(content)
                    except Exception:
                        pass
                text = content.decode("utf-8", errors="ignore")
                try:
                    return code, json.loads(text)
                except Exception:
                    return code, {"raw": text}
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", errors="ignore")
            except Exception:
                pass
            return e.code, {"error": body}
        except Exception as e:
            return 0, {"exception": str(e)}

    def _extract_jwt(self, obj):
        if isinstance(obj, str):
            if obj.startswith("eyJ") and len(obj) > 30:
                return obj
        elif isinstance(obj, dict):
            for v in obj.values():
                res = self._extract_jwt(v)
                if res:
                    return res
        elif isinstance(obj, list):
            for item in obj:
                res = self._extract_jwt(item)
                if res:
                    return res
        return ""

    def _get_guest_token(self):
        if self.cached_token:
            return self.cached_token

        url = "%s/api/guest-sessions" % self.site_url
        payload = {"device_id": str(uuid.uuid4())}
        headers = {
            "Idempotency-Key": str(uuid.uuid4()),
            "Referer": "%s/theater" % self.site_url,
            "Origin": self.site_url,
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty"
        }
        code, res = self._post_json(url, payload, headers)

        token = self._extract_jwt(res)
        if token:
            self.cached_token = token
        return token

    def _get_specials_cards(self):
        url = "%s/community/specials" % self.site_url
        code, _, _, html = self._fetch(url)
        special_links = re.findall(r'<a[^>]+href=["\'](/community/specials/[^"\']+)["\'][^>]*>([\s\S]*?)</a>', html, re.IGNORECASE)
        cards = []
        for href, inner in special_links:
            sp_id = href.replace("/community/specials/", "").replace("/", "").strip()
            
            t_m = re.search(r'<h2[^>]*>([\s\S]*?)</h2>', inner)
            title = t_m.group(1).strip() if t_m else ""
            if not title:
                continue

            c_m = re.search(r'class=["\'][^"\']*?count[^"\']*?["\'][^>]*>([\s\S]*?)</span>', inner)
            count_str = c_m.group(1) if c_m else ""
            count_str = re.sub(r'<!--.*?-->', '', count_str).strip()
            count_str = re.sub(r'<[^>]+>', '', count_str).strip()

            img_m = re.search(r'(?:src|data-src)=["\']([^"\']+)["\']', inner)
            pic = img_m.group(1) if img_m else ""
            if pic and not pic.startswith("http"):
                pic = self.cms_base + pic

            rem = "ZakaTV | %s" % count_str if count_str else "ZakaTV | 专题合集"
            cards.append({
                "vod_id": "special@@%s" % sp_id,
                "vod_name": title,
                "vod_pic": pic if pic else "https://mediacms.wtayty.cn/img/w720/catalog-covers/default.jpg",
                "vod_remarks": rem,
                "vod_actor": "📺TG群: https://t.me/+3t5XRPPo9mlkZDRl",
                "vod_director": "📺ZakaTV"
            })
        return cards

    def _format_drama_cards(self, json_data):
        cards = []
        if not json_data or not isinstance(json_data, dict):
            return cards

        data_obj = json_data.get("data")
        items = []
        if isinstance(data_obj, dict):
            items = data_obj.get("items") or []
        elif isinstance(data_obj, list):
            items = data_obj

        for it in items:
            did = str(it.get("id") or "")
            name = str(it.get("title") or "")
            cover = str(it.get("cover_url") or it.get("cover") or "")
            if cover and not cover.startswith("http"):
                cover = self.cms_base + cover

            ep = it.get("episode_count") or it.get("total_episodes") or ""
            status = it.get("serial_status") or ""
            is_completed = status == "completed"

            if is_completed:
                rem = "ZakaTV | 全 %s 集" % ep if ep else "ZakaTV | 完结"
            else:
                rem = "ZakaTV | 更新至 %s 集" % ep if ep else "ZakaTV | 连载中"

            if did and name:
                cards.append({
                    "vod_id": did,
                    "vod_name": name,
                    "vod_pic": cover,
                    "vod_remarks": rem,
                    "vod_actor": "📺TG群: https://t.me/+3t5XRPPo9mlkZDRl",
                    "vod_director": "📺ZakaTV"
                })
        return cards

    def homeContent(self, filter):
        self._check_and_refresh_domain()

        categories = [
            {"type_id": "all", "type_name": "全部短剧"},
            {"type_id": "specials_hub", "type_name": "🔥 影片专题"},
            {"type_id": "b3ac5e5e-e9c7-4c8e-8e3a-aa05bc992555", "type_name": "明星换脸"},
            {"type_id": "752db96d-909b-43bd-b351-66080e3c60c7", "type_name": "影视魔改"},
            {"type_id": "b122f913-beda-459b-8e29-34a09f5c0ef3", "type_name": "动漫游戏"},
            {"type_id": "9f36b801-2a20-4c60-a88a-8ec6cef7e639", "type_name": "家庭乱伦"},
            {"type_id": "5f334314-cfdd-40e6-b1f6-1b4eb1667646", "type_name": "穿越重生"},
            {"type_id": "b895ba5a-f8be-439d-9844-3150fff05880", "type_name": "系统异能"},
            {"type_id": "7ed80c5d-fdee-4547-b600-23043dfae566", "type_name": "仙侠修真"},
            {"type_id": "cdef9da2-c248-46db-b20e-f273d34f8dd6", "type_name": "古装权谋"},
            {"type_id": "421ddab7-af03-4881-82c8-e75ed4ee6b43", "type_name": "灵异奇幻"},
            {"type_id": "1db55d3d-7fd3-40af-aa3d-8ee2868a317c", "type_name": "同性题材"},
            {"type_id": "0407f2a8-2366-4ee4-b32e-44844451d309", "type_name": "性转伪娘"},
            {"type_id": "5fdf214a-2326-4683-b8c2-05260aff3bf8", "type_name": "婚姻背叛"},
            {"type_id": "c6577ce8-98de-4fc4-a0eb-2500d4bcee75", "type_name": "支配调教"},
            {"type_id": "34f859cf-cb80-44c6-b5e5-6dd7605c8ae0", "type_name": "偷拍偷窥"},
            {"type_id": "02ee268d-1737-4c44-9138-fbb1efb1a30c", "type_name": "公共露出"},
            {"type_id": "428adc45-d4b1-4c3b-9ef6-07a542de30ac", "type_name": "悬疑冒险"},
            {"type_id": "b185717c-670a-4157-9622-e92b87ff41d4", "type_name": "乡村艳情"},
            {"type_id": "be183a2b-7c8d-40f8-8077-3f33df80bb10", "type_name": "校园青春"},
            {"type_id": "678310ac-ce4f-415d-ba98-fcabac7238d0", "type_name": "都市职场"},
            {"type_id": "ddd0f194-64b0-44cb-a4ff-3236e6c1f478", "type_name": "医疗情色"},
            {"type_id": "af7702cf-cef7-41bf-a88d-45f70e0292c8", "type_name": "科幻末世"},
            {"type_id": "ad1d54be-e1d2-47bd-9aa3-185c5872acbe", "type_name": "人妻熟女"},
            {"type_id": "45cc019a-f7fe-496c-a579-df2a57ec77ff", "type_name": "多人派对"},
            {"type_id": "89631e80-e59d-4151-a525-6aacafffbcd9", "type_name": "情色写真"},
            {"type_id": "d699c7a3-43c5-4e3e-b1fa-660514965a01", "type_name": "日常艳遇"},
            {"type_id": "9f545357-72a3-4764-8618-3cabe529f554", "type_name": "原创短剧"}
        ]

        filters_map = {}
        status_filter = {
            "key": "serial_status",
            "name": "状态",
            "value": [
                {"n": "全部", "v": ""},
                {"n": "连载", "v": "serializing"},
                {"n": "完结", "v": "completed"}
            ]
        }
        for c in categories:
            if c["type_id"] != "specials_hub":
                filters_map[c["type_id"]] = [status_filter]

        code, res = self._fetch_api(self.api_url, {"limit": 40})
        cards = self._format_drama_cards(res)

        if isinstance(res, dict):
            data_obj = res.get("data")
            if isinstance(data_obj, dict):
                next_cur = data_obj.get("next_cursor")
                if next_cur:
                    if "all" not in self.cursor_cache:
                        self.cursor_cache["all"] = {}
                    self.cursor_cache["all"][2] = next_cur

        return {
            "class": categories,
            "filters": filters_map,
            "list": cards
        }

    def homeVideoContent(self):
        return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        if tid == "specials_hub":
            sp_cards = self._get_specials_cards()
            return {
                "list": sp_cards,
                "page": int(pg or 1),
                "pagecount": 1,
                "limit": len(sp_cards),
                "total": len(sp_cards)
            }

        page_val = int(pg or 1)
        limit_val = 40

        cache_key = tid if tid else "all"
        if cache_key not in self.cursor_cache:
            self.cursor_cache[cache_key] = {}

        params = {"limit": limit_val}
        if tid and tid != "all":
            params["category_id"] = tid

        if extend and isinstance(extend, dict):
            status_val = extend.get("serial_status")
            if status_val:
                params["serial_status"] = status_val

        if page_val > 1:
            cursor_token = self.cursor_cache[cache_key].get(page_val)
            if cursor_token:
                params["cursor"] = cursor_token

        code, res = self._fetch_api(self.api_url, params)
        cards = self._format_drama_cards(res)

        total_num = 4000
        next_cur = ""
        if isinstance(res, dict):
            data_obj = res.get("data")
            if isinstance(data_obj, dict):
                total_val = data_obj.get("total")
                if total_val:
                    total_num = int(total_val)
                next_cur = data_obj.get("next_cursor") or ""

        if next_cur:
            self.cursor_cache[cache_key][page_val + 1] = next_cur

        pagecount = (total_num + limit_val - 1) // limit_val
        if not cards:
            pagecount = page_val

        return {
            "list": cards,
            "page": page_val,
            "pagecount": pagecount,
            "limit": limit_val,
            "total": total_num
        }

    def detailContent(self, ids):
        raw_id = ids[0] if isinstance(ids, list) else ids

        if raw_id.startswith("special@@"):
            sp_id = raw_id.replace("special@@", "")
            sp_url = "%s/community/specials/%s" % (self.site_url, sp_id)
            c, _, _, html = self._fetch(sp_url)

            t_m = re.search(r'<h1[^>]*>([\s\S]*?)</h1>', html)
            sp_title = t_m.group(1).strip() if t_m else "专题剧集列表"
            sp_title = re.sub(r'<[^>]+>', '', sp_title).strip()

            drama_links = re.findall(r'<a[^>]+href=["\'](/dramas/[a-f0-9\-]+)["\'][^>]*>([\s\S]*?)</a>', html)
            play_urls = []
            seen_dids = set()
            idx = 1
            for href, block in drama_links:
                did = href.replace("/dramas/", "").replace("/", "").strip()
                if did in seen_dids:
                    continue
                seen_dids.add(did)

                d_title_m = re.search(r'<h[234][^>]*>([\s\S]*?)</h[234]>', block)
                d_title = d_title_m.group(1).strip() if d_title_m else ""
                if not d_title:
                    clean_b = re.sub(r'<[^>]+>', '', block).strip()
                    clean_b = re.sub(r'\s+', ' ', clean_b)
                    d_title = clean_b.split(" ")[0] if " " in clean_b else ("短剧%d" % idx)

                d_title = re.sub(r'<[^>]+>', '', d_title).strip()
                short_title = d_title[:14] if d_title else ("短剧%d" % idx)
                play_urls.append("%s$%s@@" % (short_title, did))
                idx += 1

            vod = {
                "vod_id": raw_id,
                "vod_name": sp_title,
                "vod_pic": "https://mediacms.wtayty.cn/img/w720/catalog-covers/default.jpg",
                "vod_type_name": "影片专题",
                "vod_year": "2026",
                "vod_area": "中国大陆",
                "vod_actor": "📺TG群: https://t.me/+3t5XRPPo9mlkZDRl",
                "vod_director": "📺ZakaTV",
                "vod_remarks": "ZakaTV | 收录 %d 部短剧" % len(play_urls),
                "vod_content": "本专题精选收录 %d 部短剧，点击下方剧集直接进入正片播放" % len(play_urls),
                "vod_play_from": "ZakaTV专题线",
                "vod_play_url": "#".join(play_urls) if play_urls else "暂无短剧$none"
            }
            return {"list": [vod]}

        episodes_api_url = "%s/api/dramas/%s/episodes" % (self.site_url, raw_id)
        code, ep_res = self._fetch_api(episodes_api_url)

        ep_list = []
        if isinstance(ep_res, dict):
            ep_list = ep_res.get("data") or ep_res.get("items") or []

        play_urls = []
        first_cover = ""
        first_title = ""
        desc = ""

        if ep_list and isinstance(ep_list, list):
            for i, ep in enumerate(ep_list):
                ep_num = ep.get("episode_number") or (i + 1)
                short_title = "第%s集" % ep_num
                ep_id = str(ep.get("id") or "")
                play_payload = "%s@@%s" % (raw_id, ep_id)
                play_urls.append("%s$%s" % (short_title, play_payload))

            first_ep = ep_list[0]
            first_cover = str(first_ep.get("cover_url") or "")
            first_title = str(first_ep.get("title") or "").split("｜")[0].strip()
            desc = str(first_ep.get("description") or "")

        if not play_urls:
            play_urls.append("第1集$%s@@" % raw_id)

        vod = {
            "vod_id": raw_id,
            "vod_name": first_title or "短剧正片",
            "vod_pic": first_cover if first_cover else "https://mediacms.wtayty.cn/img/w720/catalog-covers/default.jpg",
            "vod_type_name": "AI短剧",
            "vod_year": "2026",
            "vod_area": "中国大陆",
            "vod_actor": "📺TG群: https://t.me/+3t5XRPPo9mlkZDRl",
            "vod_director": "📺ZakaTV",
            "vod_remarks": "ZakaTV | 全 %d 集" % len(ep_list) if ep_list else "ZakaTV",
            "vod_content": desc if desc else "香蕉短剧正片播放",
            "vod_play_from": "ZakaTV专线",
            "vod_play_url": "#".join(play_urls) if play_urls else "暂无短剧$none"
        }
        return {"list": [vod]}

    def playerContent(self, flag, id, vipFlags):
        parts = id.split("@@")
        drama_id = parts[0]
        ep_id = parts[1] if len(parts) > 1 else ""

        if drama_id and not ep_id:
            episodes_api_url = "%s/api/dramas/%s/episodes" % (self.site_url, drama_id)
            code, ep_res = self._fetch_api(episodes_api_url)
            if isinstance(ep_res, dict):
                ep_list = ep_res.get("data") or []
                if ep_list:
                    ep_id = str(ep_list[0].get("id") or "")

        token = self._get_guest_token()

        session_url = "%s/api/playback/sessions" % self.site_url
        session_payload = {
            "drama_id": drama_id,
            "episode_id": ep_id
        }
        session_headers = {
            "Authorization": "Bearer %s" % token if token else "",
            "Idempotency-Key": str(uuid.uuid4()),
            "Referer": "%s/dramas/%s" % (self.site_url, drama_id),
            "Origin": self.site_url,
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty"
        }

        code, res = self._post_json(session_url, session_payload, session_headers)

        if code == 401 or (isinstance(res, dict) and "AUTH_REQUIRED" in str(res)):
            self.cached_token = ""
            token = self._get_guest_token()
            session_headers["Authorization"] = "Bearer %s" % token if token else ""
            session_headers["Idempotency-Key"] = str(uuid.uuid4())
            code, res = self._post_json(session_url, session_payload, session_headers)

        direct_url = ""
        if isinstance(res, dict):
            media_info = res.get("data", {}).get("media", {})
            direct_url = media_info.get("manifest_url", "")

        return {
            "parse": 0 if direct_url else 1,
            "url": direct_url if direct_url else "%s/dramas/%s" % (self.site_url, drama_id),
            "header": {
                "User-Agent": self.headers["User-Agent"],
                "Referer": "%s/dramas/%s" % (self.site_url, drama_id)
            }
        }

    def searchContent(self, key, quick, pg="1"):
        return {"list": []}

    def action(self, action):
        return ""

    def liveContent(self):
        return ""

    def localProxy(self, params):
        return None

    def manualVideoCheck(self):
        return False

    def isVideoFormat(self, url):
        return False

    def destroy(self):
        pass

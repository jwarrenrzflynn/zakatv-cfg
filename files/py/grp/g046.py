# -*- coding: utf-8 -*-
# 小色猫.VIP (xiaosemao.app) TVBox Python插件
# API: /app/v1/home-feed | /app/v1/contents | /app/v1/contents/{id}/play
import re
import json
import urllib.request
import urllib.parse

class Spider:
    def __init__(self):
        self.base = "https://xiaosemao.app"
        self.ua = "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36"

    def init(self, extend):
        if extend and extend.startswith("http"):
            self.base = extend.rstrip("/")

    def _get(self, url):
        req = urllib.request.Request(url, headers={
            "User-Agent": self.ua,
            "Accept": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return r.read().decode("utf-8", errors="ignore")
        except Exception:
            return ""

    def _item(self, it):
        vid = it.get("assetId", "")
        if not vid:
            return None
        name = it.get("title", vid)
        pic = it.get("posterKey", "")
        if pic.startswith("/"):
            pic = self.base + pic
        dur = it.get("durationSec", 0)
        remark = self._fmt_dur(dur) if dur else "在线"
        return {
            "vod_id": vid,
            "vod_name": name,
            "vod_pic": pic,
            "vod_remarks": remark,
        }

    def _fmt_dur(self, sec):
        h, m, s = sec // 3600, (sec % 3600) // 60, sec % 60
        if h > 0:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"

    def homeContent(self, filter):
        classes = [
            {"type_name": "吃瓜", "type_id": "chigua"},
            {"type_name": "女优", "type_id": "riben-nvyou"},
            {"type_name": "素人", "type_id": "riben-suren"},
            {"type_name": "麻豆", "type_id": "chuanmei-madou"},
            {"type_name": "国内主播", "type_id": "guonei-zhubo"},
            {"type_name": "91制片", "type_id": "chuanmei-jiuyi"},
            {"type_name": "SA国际", "type_id": "chuanmei-sa"},
            {"type_name": "大象传媒", "type_id": "chuanmei-daxiang"},
            {"type_name": "主播", "type_id": "guochan-zhubo"},
            {"type_name": "韩国直播", "type_id": "zhibo-hanguo"},
            {"type_name": "圈内直播", "type_id": "zhibo-zhongguo"},
            {"type_name": "主播禁区", "type_id": "douyin"},
            {"type_name": "刷视频", "type_id": "duanshipin"},
        ]
        data = self._get(self.base + "/app/v1/home-feed")
        lst = []
        try:
            d = json.loads(data)
            for sec in d.get("sections", []):
                for it in sec.get("items", []):
                    v = self._item(it)
                    if v:
                        lst.append(v)
        except Exception:
            pass
        return json.dumps({"class": classes, "list": lst}, ensure_ascii=False)

    def homeVideoContent(self):
        data = self._get(self.base + "/app/v1/home-feed")
        lst = []
        try:
            d = json.loads(data)
            for sec in d.get("sections", []):
                for it in sec.get("items", []):
                    v = self._item(it)
                    if v:
                        lst.append(v)
        except Exception:
            pass
        return json.dumps({"list": lst}, ensure_ascii=False)

    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg) if pg and pg.isdigit() else 1
        url = f"{self.base}/app/v1/contents?channelSlug={tid}&sort=discover&limit=40"
        if page > 1:
            url += f"&page={page}"
        data = self._get(url)
        lst = []
        try:
            d = json.loads(data)
            for it in d.get("items", []):
                v = self._item(it)
                if v:
                    lst.append(v)
        except Exception:
            pass
        return json.dumps({
            "page": page,
            "pagecount": page + 1 if len(lst) >= 40 else page,
            "limit": len(lst),
            "total": 999999 if len(lst) >= 40 else len(lst),
            "list": lst,
        }, ensure_ascii=False)

    def detailContent(self, ids):
        vid = ids[0]
        data = self._get(f"{self.base}/app/v1/contents/{vid}")
        lst = []
        try:
            d = json.loads(data)
            name = d.get("title", vid)
            pic = d.get("posterKey", "")
            if pic.startswith("/"):
                pic = self.base + pic
            dur = d.get("durationSec", 0)
            tags = d.get("tags", [])
            content = ",".join(tags) if tags else ""
            lst.append({
                "vod_id": vid,
                "vod_name": name,
                "vod_pic": pic,
                "vod_remarks": self._fmt_dur(dur) if dur else "在线",
                "vod_content": content,
                "vod_play_from": "小色猫",
                "vod_play_url": f"播放${vid}",
            })
        except Exception:
            pass
        return json.dumps({"list": lst}, ensure_ascii=False)

    def playerContent(self, flag, id, vipFlags):
        vid = id.split("$")[-1] if "$" in id else id
        data = self._get(f"{self.base}/app/v1/contents/{vid}/play")
        play_url = ""
        try:
            d = json.loads(data)
            play_url = d.get("url", "")
        except Exception:
            pass
        if not play_url:
            play_url = f"{self.base}/app/v1/contents/{vid}/hls.m3u8"
        return json.dumps({"parse": 0, "url": play_url, "header": ""}, ensure_ascii=False)

    def searchContent(self, key, quick):
        kw = urllib.parse.quote(key)
        url = f"{self.base}/app/v1/contents?q={kw}&limit=40"
        data = self._get(url)
        lst = []
        try:
            d = json.loads(data)
            for it in d.get("items", []):
                v = self._item(it)
                if v:
                    lst.append(v)
        except Exception:
            pass
        return json.dumps({"list": lst}, ensure_ascii=False)

if __name__ == "__main__":
    s = Spider()
    s.init("")
    print("home:", s.homeContent(False)[:200])
    print("cat:", s.categoryContent("riben-nvyou", "1", False, {})[:200])
    print("search:", s.searchContent("FC2", False)[:200])

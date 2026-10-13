#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
35Awards 摄影赏析 —— CatVod / 影视仓 base.spider 风格源插件

抓取 35awards.com 的摄影师列表与作品集，以 pics:// 播放串输出图片数组。
运行环境需提供 base.spider 模块，并安装 requests、urllib3。
"""

import re
import requests
from base.spider import Spider
from urllib3 import disable_warnings

disable_warnings()

UA = "Mozilla/5.0"


class Spider(Spider):
    host = "https://35awards.com"

    # ------------------------------------------------------------------ #
    # 元信息
    # ------------------------------------------------------------------ #
    def getName(self):
        return "35Awards摄影赏析"

    def init(self, extend=""):
        pass

    # ------------------------------------------------------------------ #
    # 首页分类
    # ------------------------------------------------------------------ #
    def homeContent(self, filter):
        classes = [
            {"type_id": "/en/authors/ru/nude/", "type_name": "人体艺术 (Nude)"},
            {"type_id": "/en/authors/genre/fashion/", "type_name": "时尚摄影 (Fashion)"},
        ]
        return {"class": classes}

    # ------------------------------------------------------------------ #
    # 分类列表 + 分页
    # ------------------------------------------------------------------ #
    def categoryContent(self, tid, pg, filter, extend):
        curr_pg = int(pg)
        # 翻页 URL：第 1 页无后缀，第 2 页起为 {tid}page/{n}/
        if curr_pg > 1:
            url = f"{self.host}{tid}page/{curr_pg}/"
        else:
            url = f"{self.host}{tid}"

        res = requests.get(url, verify=False, timeout=10, headers={"User-Agent": UA})
        html = res.text

        # 匹配摄影师（影片）卡片：捕获 链接 / author_id / 封面图 / 作者名
        matches = re.findall(
            r'authorHeader">.*?href="([^"]+author/([^/]+)/)".*?src="([^"]+)".*?itemprop="name">([^<]+)</span>',
            html,
            re.S,
        )

        vod_list = []
        for link, author_id, pic, name in matches:
            vod_list.append({
                "vod_id": author_id,
                "vod_name": name.strip(),
                "vod_pic": pic,
                "vod_remarks": "点击查看作品集",
            })

        # 翻页逻辑：页面含 next-page 或本页条目足够多，则还有下一页
        has_next = "next-page" in html or len(vod_list) >= 12
        last_page = curr_pg + 1 if has_next else curr_pg

        return {
            "page": curr_pg,
            "pagecount": last_page,
            "limit": len(vod_list),
            "total": 999,
            "list": vod_list,
        }

    # ------------------------------------------------------------------ #
    # 详情 + 作品集播放串
    # ------------------------------------------------------------------ #
    def detailContent(self, ids):
        author_id = ids[0]
        url = f"{self.host}/en/author/{author_id}/"
        res = requests.get(url, verify=False, timeout=10, headers={"User-Agent": UA})
        html = res.text

        # 1. 基本信息：作者名 + 头像
        name_match = re.search(r'<h1[^>]*>([^<]+)</h1>', html)
        pic_match = re.search(r'class="authorAvatar">.*?src="([^"]+)"', html, re.S)

        # 2. 作品图数组（缩略图在 data-src，class 含 lozadGridPhoto）
        img_matches = re.findall(r'class="[^"]*lozadGridPhoto[^"]*"[^>]+data-src="([^"]+)"', html)

        # 3. 图片直链补全
        clean_imgs = []
        for img in img_matches:
            if img.startswith('//'):
                img = "https:" + img
            elif img.startswith('/'):
                img = self.host + img
            clean_imgs.append(img)

        # 4. 拼装 pics:// 播放串：来源$线路1&&线路2&&...
        play_url = "作品集$" + "pics://" + "&&".join(clean_imgs)

        vod = {
            "vod_id": author_id,
            "vod_name": name_match.group(1).strip() if name_match else author_id,
            "vod_pic": pic_match.group(1) if pic_match else "",
            "vod_play_from": "35Awards",
            "vod_play_url": play_url,
            "vod_content": f"摄影师 {author_id} 的精选作品集。",
        }

        return {"list": [vod]}

    # ------------------------------------------------------------------ #
    # 搜索（本源未实现，返回空）
    # ------------------------------------------------------------------ #
    def searchContent(self, key, quick, pg="1"):
        return {"list": []}

    # ------------------------------------------------------------------ #
    # 播放器直链
    # ------------------------------------------------------------------ #
    def playerContent(self, flag, id, vipFlags):
        return {
            "parse": 0,
            "url": id,
            "header": {"User-Agent": UA},
        }

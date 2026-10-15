# -*- coding: utf-8 -*-
"""
爱液视频（aiye 系）· TVBox Python 插件 · 纯标准库自实现（不需要 requests）
=====================================================================================
接口： homeContent / homeVideoContent / categoryContent / detailContent / searchContent / playerContent
挂法： {"name":"🆕🔞爱液视频┃官方App接口","type":3,"api":"py_爱液视频.py"}
       （extend 可传 {"host":"https://xxxx.aiyejikou0001.com"} 手动钉一个接口域）

【站情 · 2026-10-14 逆向官方包 爱液视频_2.1.0.apk（22MB / Kotlin / 5 个 dex），全部真站实测】
  包被 dpt-shell（luoyesiqiu 开源壳）加固：真 dex 压成 zip 贴在壳 dex 尾部，方法体被抹掉、运行期由
  native 还原（AES-CBC + RC4，RC4 密钥是 so 里明文的 1234567890abcdef）。
  ★ 但接口定义是 Retrofit 注解 + 常量池字符串，不在方法体里，所以注解一条不漏地抠了出来。
  本插件只取「在线视频库」这一条链（社区 / 听书 / 图集 / 会员 / 任务没动）。

  接口基址是**动态下发**的（DNS TXT），见下面「域自举」。
    导航     GET /api/home/indextypelist?types=1&type=0            → 23 个顶级分类
    子分类   GET /api/home/indextypelist?types=1&type={topId}      → 该顶级下的子分类 + 10 条预览
    收录组   GET /api/home/indextaglist                            → 首页 12 个「收录」组
    分类列表 GET /api/vod/list?types={subId}&page={n}              20 条/页 + total
    标签列表 GET /api/vod/list?labels={labelId}&page={n}           首页「收录」组走这条
    搜索     GET /api/vod/clever?wd={关键词}&page={n}              20 条/页 + total（主库搜索）
    详情     GET /api/vod/info?id={vodId}                          → play_url（带签名 m3u8）
    线路     GET /api/vod/line/list?vodid={vodId}                  → 默认线路 / 快速线路
    相关     GET /api/vod/recommend?id={vodId}&page={n}
    热词     GET /api/vod/hotsearchword
    标签库   GET /api/vodlabel/all                                 486 个标签

  ★ 三个「参数名坑」（一条条爆出来的，记下来免得再踩）：
    ① 分类列表的参数是 **types**（带 s），不是 type_id / typeid —— 后两个传了被无视，返回全库。
    ② 搜索走 /api/vod/clever?wd= ，不是 /api/vod/list?keyword= —— keyword 传了同样被无视。
    ③ 首页「收录」组（indextaglist 那 12 组）走 /api/vod/list?labels={组id} 。
  另：APP 侧请求带 x-appid / x-token / terminalType 三个头；实测**公开读接口全部免鉴权免签名**，
      头带了不亏、不带也不挡（本插件照样挂着）。

【域自举 —— 这站没有固定域名，别写死】
  hostnew.aiye.me  TXT → base64( {"url":["https://0826.aiyejikou0001.com", ... 0002/0003/0004]} )
  host.aiye.me     TXT → 明文单条 URL
  顺序：extend.host 覆盖 > hostnew 自举（4 节点轮询）> host 明文兜底 > 内置池。
  缓存 30 分钟，某节点打不响自动换下一个；全池死光也不瘫，把新域填进 extend.host 立刻复活。

【取流 —— 干净，不用破，但要「现取现播」】
  详情 / 线路口返回的是**站方服务端签好名的 m3u8**（?t=时间戳&sign=md5），播放器直连即可：
  实测 HLS 主清单 200 / 24563 字节，分片是标准 TS，带 **AES-128 的 #EXT-X-KEY**（壳原生支持）。
  ⚠️ 地址带签名有时效，所以播放时**重取一次线路、不缓存 m3u8 地址**（线路口就几百字节 JSON）。

自检： python3 爱液视频-TVBox插件.py
"""

import base64
import json
import time
import urllib.error
import urllib.parse
import urllib.request

SITE_NAME = '爱液视频'
UA = 'okhttp/4.9.0'
APPID = 'com.aayydd.bsd'

# DoH 自举入口（hostnew 给整池，host 给单条）
TXT_POOL = 'https://dns.alidns.com/resolve?name=hostnew.aiye.me&short=true&type=16'
TXT_ONE = 'https://dns.alidns.com/resolve?name=host.aiye.me&short=true&type=16'
TXT_POOL2 = 'https://doh.pub/dns-query?name=hostnew.aiye.me&type=TXT'

# 内置兜底池（DNS 全挂了才用；域会变，变了在 extend 里改，不用改文件）
BUILTIN = [
    'https://0826.aiyejikou0001.com',
    'https://0826.aiyejikou0002.com',
    'https://0826.aiyejikou0003.com',
    'https://0826.aiyejikou0004.com',
]

P_NAV = '/api/home/indextypelist?types=1&type='
P_LIST = '/api/vod/list?'
P_SEARCH = '/api/vod/clever?wd='
P_INFO = '/api/vod/info?id='
P_LINE = '/api/vod/line/list?vodid='
P_TAG = '/api/home/indextaglist'

PAGE_SIZE = 20
TIMEOUT = 15
HOST_TTL = 30 * 60          # 接口域缓存 30 分钟
JSON_TTL = 3 * 60           # 列表/详情缓存 3 分钟，壳里来回翻页不重复打站

SEP = '@'                   # 播放地址 id 分隔符： vodid@线路下标


# ==================================================================== 基础 HTTP
def _hdr():
    return {
        'User-Agent': UA,
        'Accept': 'application/json, text/plain, */*',
        'x-appid': APPID,
        'terminalType': 'android',
    }


def _http(url, timeout=TIMEOUT):
    req = urllib.request.Request(url, headers=_hdr())
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', 'replace')


def _txt(doh):
    """读一条 DNS TXT，返回去掉外层引号的字符串"""
    try:
        s = _http(doh, timeout=8).strip()
        if not s:
            return None
        if s.startswith('['):
            arr = json.loads(s)
            if not arr:
                return None
            s = arr[0] if isinstance(arr[0], str) else ''
        elif '"data"' in s:
            # doh.pub / dns.google 的 JSON 形态
            try:
                j = json.loads(s)
                s = (j.get('data') or j.get('Answer', [{}])[0].get('data') or '')
            except Exception:
                k = s.find('"data"')
                if k < 0:
                    return None
                q1 = s.find('"', s.find(':', k) + 1)
                q2 = s.find('"', q1 + 1)
                if q1 < 0 or q2 <= q1:
                    return None
                s = s[q1 + 1:q2]
        return s.strip().strip('"').strip()
    except Exception:
        return None


def _b64d(s):
    """宽松 base64 解码（失败返回 None；解出来必须像 JSON 才认）"""
    if not s:
        return None
    try:
        t = s.strip()
        t += '=' * (-len(t) % 4)
        d = base64.b64decode(t).decode('utf-8', 'replace')
        return d if '{' in d else None
    except Exception:
        return None


def _norm(u):
    if not u:
        return ''
    t = str(u).strip()
    if not t:
        return ''
    if not t.startswith('http'):
        t = 'https://' + t
    return t.rstrip('/')


# ==================================================================== 壳契约
try:
    from spider import Spider as _BaseSpider          # TVBox 壳里真实基类
except Exception:
    class _BaseSpider(object):                        # 原生 python 下自检用
        def __init__(self, *a, **kw):
            pass

        def init(self, *a, **kw):
            return self


class Spider(_BaseSpider):

    def __init__(self, *args, **kwargs):
        try:
            super(Spider, self).__init__(*args, **kwargs)
        except Exception:
            pass
        self.ext_host = ''
        self._hosts = []
        self._host_ts = 0.0
        self._host_idx = 0
        self._cache = {}

    # ---------- 生命周期 ----------
    def init(self, extend=''):
        self.ext_host = self._pick_host(extend)
        if self.ext_host:
            self._hosts = [self.ext_host]
            self._host_ts = time.time()
            self._host_idx = 0
        return self

    def getName(self):
        return SITE_NAME

    def destroy(self):
        self._cache.clear()

    def isVideoFormat(self, url):
        u = (url or '').lower()
        return '.m3u8' in u or '.ts' in u or '.mp4' in u

    def manualVideoCheck(self):
        return False

    @staticmethod
    def _pick_host(extend):
        if not extend:
            return ''
        e = extend.strip() if isinstance(extend, str) else ''
        if not e:
            return ''
        if e.startswith('{'):
            try:
                return _norm(json.loads(e).get('host', ''))
            except Exception:
                return ''
        return _norm(e)

    # ---------- 域自举 ----------
    def _base(self):
        now = time.time()
        if self._hosts and now - self._host_ts < HOST_TTL:
            if not (0 <= self._host_idx < len(self._hosts)):
                self._host_idx = 0
            return self._hosts[self._host_idx]
        self._refresh_hosts()
        if not (0 <= self._host_idx < len(self._hosts)):
            self._host_idx = 0
        return self._hosts[self._host_idx] if self._hosts else BUILTIN[0]

    def _rotate(self):
        """当前节点打不响 → 换下一个，并逼下次重新自举"""
        if len(self._hosts) > 1:
            self._host_idx = (self._host_idx + 1) % len(self._hosts)
        self._host_ts = 0.0

    def _refresh_hosts(self):
        got = []
        if self.ext_host:
            got.append(self.ext_host)

        pool = _txt(TXT_POOL) or _txt(TXT_POOL2)
        j = _b64d(pool)
        if j:
            try:
                for u in (json.loads(j).get('url') or []):
                    u = _norm(u)
                    if u and u not in got:
                        got.append(u)
            except Exception:
                pass
        if not got:
            one = _norm(_txt(TXT_ONE))
            if one:
                got.append(one)
        if not got:
            got = list(BUILTIN)

        # 实测探活：第一个能出 JSON 的当本线，别把死节点排前面
        for i, h in enumerate(list(got)):
            try:
                probe = _http(h + P_NAV + '0', timeout=TIMEOUT)
            except Exception:
                continue
            if probe and '"code":200' in probe:
                got.insert(0, got.pop(i))
                break

        self._hosts = got
        self._host_ts = time.time()
        self._host_idx = 0

    # ---------- 取数据 ----------
    def _api(self, path):
        """请求 JSON；节点打不响自动换一个（最多把所有节点试一遍）"""
        last = None
        for _ in range(3):
            try:
                body = _http(self._base() + path, timeout=TIMEOUT)
            except Exception:
                body = None
            if body:
                try:
                    o = json.loads(body)
                    if int(o.get('code', 0) or 0) == 200:
                        return o
                    last = o
                except Exception:
                    pass
            self._rotate()
        if last is not None:
            return last
        return None

    @staticmethod
    def _data_list(o):
        if not o:
            return []
        d = o.get('data')
        if not isinstance(d, dict):
            return []
        l = d.get('list')
        return l if isinstance(l, list) else []

    @staticmethod
    def _total(o):
        if not o:
            return 0
        d = o.get('data')
        if not isinstance(d, dict):
            return 0
        try:
            return int(d.get('total', 0) or 0)
        except Exception:
            return 0

    # ---------- 卡片 ----------
    @staticmethod
    def _remark(it):
        sb = []
        try:
            dur = int(it.get('duration', 0) or 0)
        except Exception:
            dur = 0
        if dur > 0:
            m = dur // 60
            sb.append(('%d 时 %d 分' % (m // 60, m % 60)) if m >= 60 else ('%d 分钟' % m))
        try:
            views = int(it.get('views', 0) or 0)
        except Exception:
            views = 0
        if views > 0:
            sb.append(('%d万播放' % (views // 10000)) if views >= 10000 else ('%d 播放' % views))
        return ' · '.join(sb)

    def _card(self, it):
        vid = str(it.get('id', '') or '')
        title = str(it.get('title', '') or '')
        return {
            'vod_id': vid,
            'vod_name': title or ('视频 ' + vid),
            'vod_pic': str(it.get('cover', '') or ''),
            'vod_remarks': self._remark(it),
        }

    @staticmethod
    def _folder(fid, name, pic, note):
        return {
            'vod_id': fid,
            'vod_name': name,
            'vod_pic': pic,
            'vod_remarks': note,
            'vod_tag': 'folder',
        }

    # ---------- 首页 ----------
    def homeContent(self, filter=False):
        classes = []
        items = []

        tops = self._data_list(self._api(P_NAV + '0'))
        for c in tops:
            if not isinstance(c, dict):
                continue
            cid = str(c.get('id', '') or '')
            if not cid:
                continue
            classes.append({'type_id': 'T' + cid, 'type_name': str(c.get('name', '') or '')})

        for g in self._data_list(self._api(P_TAG)):
            if not isinstance(g, dict):
                continue
            gid = str(g.get('id', '') or '')
            if not gid:
                continue
            pre = g.get('list') if isinstance(g.get('list'), list) else []
            pic = str(pre[0].get('cover', '') or '') if pre and isinstance(pre[0], dict) else ''
            items.append(self._folder('L' + gid, str(g.get('name', '') or ''), pic,
                                      '%d 部精选' % len(pre)))

        # 收录组一个都没拉到（接口抽风）→ 退回到拿顶级分类的预览当首页推荐
        if not items:
            for c in tops:
                if not isinstance(c, dict):
                    continue
                cid = str(c.get('id', '') or '')
                sub = [x for x in self._data_list(self._api(P_NAV + cid)) if isinstance(x, dict)]
                if not sub:
                    continue
                items.append(self._folder('T' + cid, str(c.get('name', '') or ''),
                                          str(sub[0].get('cover', '') or ''),
                                          '%d 个子分类' % len(sub)))

        return json.dumps({'class': classes, 'list': items}, ensure_ascii=False)

    def homeVideoContent(self):
        return json.dumps({'list': []}, ensure_ascii=False)

    # ---------- 分类 ----------
    def categoryContent(self, tid, pg, filter=False, extend=None):
        try:
            page = int(str(pg).strip())
        except Exception:
            page = 1
        if page < 1:
            page = 1
        tid = (tid or '').strip()

        # T{顶级} → 该顶级下的子分类墙（点进去才是列表）
        if tid.startswith('T'):
            subs = [x for x in self._data_list(self._api(P_NAV + tid[1:])) if isinstance(x, dict)]
            lst = []
            for c in subs:
                pre = c.get('list') if isinstance(c.get('list'), list) else []
                pic = str(pre[0].get('cover', '') or '') if pre and isinstance(pre[0], dict) else ''
                lst.append(self._folder(str(c.get('id', '') or ''), str(c.get('name', '') or ''),
                                        pic, '%d 部精选' % len(pre)))
            return json.dumps({'page': 1, 'pagecount': 1, 'limit': PAGE_SIZE,
                               'total': len(lst), 'list': lst}, ensure_ascii=False)

        if tid.startswith('L'):
            resp = self._api(P_LIST + 'labels=' + tid[1:] + '&page=' + str(page))
        else:
            resp = self._api(P_LIST + 'types=' + tid + '&page=' + str(page))

        arr = self._data_list(resp)
        lst = [self._card(it) for it in arr if isinstance(it, dict)]
        total = self._total(resp)
        if total > 0:
            pagecount = (total + PAGE_SIZE - 1) // PAGE_SIZE
        else:
            pagecount = page if len(lst) >= PAGE_SIZE else page + 1
        return json.dumps({'page': page, 'pagecount': pagecount, 'limit': PAGE_SIZE,
                           'total': total if total > 0 else len(lst), 'list': lst},
                          ensure_ascii=False)

    # ---------- 详情 ----------
    def detailContent(self, ids):
        vid = str(ids[0]) if ids else ''
        resp = self._api(P_INFO + vid)
        d = resp.get('data') if isinstance(resp, dict) else None
        if not isinstance(d, dict):
            d = {}

        name = str(d.get('title', '') or '')
        vod = {
            'vod_id': vid,
            'vod_name': name or ('视频 ' + vid),
            'vod_pic': str(d.get('cover', '') or ''),
            'vod_content': self._content(d),
        }

        lines = [x for x in self._data_list(self._api(P_LINE + vid)) if isinstance(x, dict)]
        froms, urls = [], []
        for i, ln in enumerate(lines):
            if not str(ln.get('domain', '') or ''):
                continue
            lname = str(ln.get('name', '') or '') or ('线路%d' % (i + 1))
            froms.append(lname)
            urls.append('%s$%s%s%d' % (lname, vid, SEP, i))
        if not froms:
            if str(d.get('play_url', '') or ''):
                froms.append('默认线路')
                urls.append('默认线路$%s%s0' % (vid, SEP))

        vod['vod_play_from'] = '$$$'.join(froms)
        vod['vod_play_url'] = '$$$'.join(urls)
        vod['vod_remarks'] = ('%d 条线路' % len(froms)) if froms else '暂无可播线路'

        return json.dumps({'list': [vod]}, ensure_ascii=False)

    @staticmethod
    def _content(d):
        sb = []
        pid = str(d.get('id', '') or '')
        if pid:
            sb.append('片号：' + pid)
        labels = d.get('labels') if isinstance(d.get('labels'), list) else []
        tags = [str(l.get('name', '') or '') for l in labels if isinstance(l, dict)]
        tags = [t for t in tags if t]
        if tags:
            sb.append('标签：' + ' / '.join(tags))
        try:
            views = int(d.get('views', 0) or 0)
            fav = int(d.get('favorites', 0) or 0)
        except Exception:
            views = fav = 0
        if views > 0 or fav > 0:
            sb.append('播放 %d · 收藏 %d' % (views, fav))
        return '\n'.join(sb)

    # ---------- 搜索 ----------
    def searchContent(self, key, quick=False, pg='1'):
        try:
            page = int(str(pg).strip())
        except Exception:
            page = 1
        if page < 1:
            page = 1
        kw = (key or '').strip()
        if not kw:
            return json.dumps({'list': []}, ensure_ascii=False)
        resp = self._api(P_SEARCH + urllib.parse.quote(kw, safe='') + '&page=' + str(page))
        arr = self._data_list(resp)
        return json.dumps({'list': [self._card(it) for it in arr if isinstance(it, dict)]},
                          ensure_ascii=False)

    # ---------- 播放 ----------
    def playerContent(self, flag, vid, vipFlags=None):
        raw = str(vid or '').strip()
        vod_id, idx = raw, 0
        k = raw.rfind(SEP)
        if k > 0:
            vod_id = raw[:k]
            try:
                idx = int(raw[k + 1:])
            except Exception:
                idx = 0

        url = ''
        lines = [x for x in self._data_list(self._api(P_LINE + vod_id)) if isinstance(x, dict)]
        if 0 <= idx < len(lines):
            url = str(lines[idx].get('domain', '') or '')
        if not url and lines:
            url = str(lines[0].get('domain', '') or '')       # 线路换了顺序也照样能播
        if not url:
            d = self._api(P_INFO + vod_id)
            d = d.get('data') if isinstance(d, dict) else None
            url = str((d or {}).get('play_url', '') or '')

        return json.dumps({
            'parse': 0,
            'playUrl': '',
            'url': url,
            'header': json.dumps({'User-Agent': UA}, ensure_ascii=False),
        }, ensure_ascii=False)


# ==================================================================== 自检（真站实打）
if __name__ == '__main__':
    P = F = 0

    def chk(name, cond, extra=''):
        global P, F
        if cond:
            P += 1
            print('  [PASS] %s %s' % (name, extra))
        else:
            F += 1
            print('  [FAIL] %s %s' % (name, extra))

    def cut(s, n=70):
        s = s or ''
        return s if len(s) <= n else s[:n] + '…'

    print('\n================ 爱液视频 · py 真站自检 ================')
    sp = Spider()
    sp.init('')

    # ① 域自举
    base = sp._base()
    print('[base] %s   池=%d' % (base, len(sp._hosts)))
    chk('域自举出池', base.startswith('http') and len(sp._hosts) >= 1,
        '→ ' + base + ' 池 ' + str(len(sp._hosts)))

    # ② 首页
    h = json.loads(sp.homeContent(True))
    cls, hl = h.get('class', []), h.get('list', [])
    print('[home] 顶级分类=%d 收录组=%d' % (len(cls), len(hl)))
    print('       ' + ' | '.join('%s:%s' % (c['type_id'], c['type_name']) for c in cls[:8]))
    chk('home 顶级分类=23', len(cls) == 23, '→ %d' % len(cls))
    chk('home 收录组有货', len(hl) >= 8, '→ %d 组' % len(hl))
    if hl:
        print('       首组: %s id=%s tag=%s' % (cut(hl[0]['vod_name'], 30), hl[0]['vod_id'],
                                                hl[0].get('vod_tag')))
        chk('收录组是 folder', hl[0].get('vod_tag') == 'folder', '')

    # ③ 子分类墙
    wall = json.loads(sp.categoryContent('T132', '1', False, None))
    wl = wall.get('list', [])
    chk('子分类墙 女神有子分类', len(wl) >= 10, '→ %d' % len(wl))
    sub_id = wl[0]['vod_id'] if wl else None
    if wl:
        print('       首个子分类: %s id=%s %s' % (cut(wl[0]['vod_name'], 20), sub_id,
                                                  wl[0]['vod_remarks']))

    # ④ 分类翻页
    c1 = json.loads(sp.categoryContent('136', '1', False, None))
    c2 = json.loads(sp.categoryContent('136', '2', False, None))
    l1, l2 = c1.get('list', []), c2.get('list', [])
    chk('分类 p1 = 20 条', len(l1) == 20, '→ %d' % len(l1))
    chk('分类 p2 = 20 条', len(l2) == 20, '→ %d' % len(l2))
    ov = len(set(x['vod_id'] for x in l1) & set(x['vod_id'] for x in l2))
    chk('分类两页不重复', l1 and l2 and ov == 0, '重叠=%d' % ov)
    chk('分类 total 合理', c1.get('total', 0) > 500, 'total=%d' % c1.get('total', 0))
    if l1:
        print('       p1 首条: %s  id=%s | %s' % (cut(l1[0]['vod_name'], 34), l1[0]['vod_id'],
                                                  l1[0]['vod_remarks']))

    # ⑤ 子分类出片
    if sub_id:
        cs = json.loads(sp.categoryContent(sub_id, '1', False, None))
        chk('子分类可出片', len(cs.get('list', [])) > 0,
            'id=%s → %d 条 total=%s' % (sub_id, len(cs.get('list', [])), cs.get('total')))

    # ⑥ 收录组出片
    if hl:
        cg = json.loads(sp.categoryContent(hl[0]['vod_id'], '1', False, None))
        chk('收录组可出片', len(cg.get('list', [])) > 0,
            '%s → %d 条 total=%s' % (hl[0]['vod_id'], len(cg.get('list', [])), cg.get('total')))

    # ⑦ 详情 + 线路
    vid = l1[0]['vod_id'] if l1 else None
    if vid:
        det = json.loads(sp.detailContent([vid]))
        dl = det.get('list', [])
        chk('详情有返回', len(dl) == 1, '')
        if dl:
            vd = dl[0]
            print('       详情: %s\n       线路: %s\n       playurl: %s'
                  % (cut(vd['vod_name'], 30), vd['vod_play_from'], cut(vd['vod_play_url'], 70)))
            chk('详情标题非空', bool(vd['vod_name']), '')
            chk('详情有播放线路', bool(vd['vod_play_from']) and '$' in vd['vod_play_url'],
                'from=' + vd['vod_play_from'])

        # ⑧ 播放：现取现播
        pl = json.loads(sp.playerContent('默认线路', vid + '@0', None))
        pu = pl.get('url', '')
        print('       播放地址: %s' % cut(pu, 95))
        chk('播放地址非空', len(pu) > 10, '')
        chk('播放地址是 m3u8', '.m3u8' in pu, '')
        chk('播放地址带签名', 'sign=' in pu, '')
        if len(pu) > 10:
            try:
                body = _http(pu, timeout=20)
                ok = '#EXTM3U' in body
            except Exception:
                body, ok = '', False
            chk('播放地址真拉 200 且是 HLS', ok, '→ %dB' % len(body))
            if ok:
                print('       HLS 头: %s' % cut(body.replace('\n', ' '), 110))
                print('       AES-128 加密分片: %s'
                      % ('是（壳原生支持）' if '#EXT-X-KEY' in body else '否（明文 TS）'))
        pl9 = json.loads(sp.playerContent('线路', vid + '@9', None))
        chk('线路下标越界有兜底', len(pl9.get('url', '')) > 10, '→ ' + cut(pl9.get('url', ''), 50))

    # ⑨ 搜索
    s1 = json.loads(sp.searchContent('探花', False, '1'))
    s2 = json.loads(sp.searchContent('探花', False, '2'))
    s3 = json.loads(sp.searchContent('伪娘', False, '1'))
    a1, a2, a3 = s1.get('list', []), s2.get('list', []), s3.get('list', [])
    chk('搜索 探花 p1 有货', len(a1) > 0, '→ %d' % len(a1))
    if a1:
        print('       探花首条: %s' % cut(a1[0]['vod_name'], 36))
    ovs = len(set(x['vod_id'] for x in a1) & set(x['vod_id'] for x in a2))
    chk('搜索两页不重复', bool(a1) and ovs == 0, '重叠=%d' % ovs)
    ovw = len(set(x['vod_id'] for x in a1) & set(x['vod_id'] for x in a3))
    chk('搜索两词结果不同', bool(a1) and bool(a3) and ovw < len(a1) // 2,
        '探花%d ∩ 伪娘%d = %d' % (len(a1), len(a3), ovw))
    if a3:
        print('       伪娘首条: %s' % cut(a3[0]['vod_name'], 36))
    chk('搜索无结果不崩',
        isinstance(json.loads(sp.searchContent('zzzqqq不存在词zzz', False, '1')).get('list'), list), '')

    # ⑩ 搜索出来的片能直接播
    if a1:
        d2 = json.loads(sp.detailContent([a1[0]['vod_id']]))
        v2 = d2.get('list', [{}])[0]
        chk('搜索结果可进详情', bool(v2.get('vod_name')),
            cut(v2.get('vod_name'), 26) + ' | ' + v2.get('vod_play_from', ''))

    print('\n================ 结果: %d PASS / %d FAIL ================' % (P, F))
    raise SystemExit(1 if F else 0)

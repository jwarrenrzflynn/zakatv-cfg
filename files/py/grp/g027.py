# shawn

import base64
import html as html_lib
import json
import os
import re
import threading
import time
from urllib.parse import urlencode, urljoin, urlparse

try:
    import requests
except Exception:                       # 独立跑(测试)时的兜底
    requests = None

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        pass


SITE = "https://xiuren.biz"
API = SITE + "/wp-json/wp/v2"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

# 热门榜单(站点自己维护的榜页,HTML 解析;路径后面自动接 page/N/)
HOT_BOARDS = [("month", "🔥 本月热门", "/popular-this-month/"),
              ("week", "🔺 本周热门", "/popular-this-week/")]
HOT_PATH = dict((k, p) for k, _n, p in HOT_BOARDS)
HOT_NAME = dict((k, n) for k, n, _p in HOT_BOARDS)

# 分类兜底(接口挂了也能用;正常运行时以接口拉到的为准)
CATS_FALLBACK = [
    ("xiuren", "XiuRen"), ("hot-girl", "Hot Girl"), ("xiuren-extra", "XiuRen Extra"),
    ("ugirls", "Ugirls"), ("youmi", "YouMi"), ("xiaoyu", "XiaoYu"),
    ("xingyan", "XINGYAN"), ("huayang", "HuaYang"), ("imiss", "IMISS"),
    ("feilin", "FeiLin"), ("ai-generated", "AI Generated"), ("djawa", "DJAWA"),
    ("mfstar", "MFStar"), ("cosplay", "Cosplay"), ("mygirl", "MyGirl"),
    ("miitao", "MiiTao"), ("mistar", "MiStar"), ("youwu", "YouWu"),
]

CACHE_DETAIL = 600                      # 详情(图集)缓存秒数
CACHE_CAT = 1800                        # 分类表缓存秒数
CACHE_SUB = 3600                        # 小分类(标签聚合)缓存秒数
LIST_TTL = 120                          # 列表默认缓存秒数
HOT_TTL = 300                           # 榜单缓存秒数
REQ_GAP = 0.18                          # 两次请求最小间隔,别把站拍疼了
SUB_MAX = 60                            # 一个小分类列表最多列多少个
PAGE_MAX = 60                           # 单条流最多往后翻多少页
QMAX = 8                                # 内存里最多留几个看图队列

_IMG_OK = re.compile(r"\.(?:jpe?g|png|webp|gif|bmp|avif)(?:\?|#|$)", re.I)
_IMG_BAD = re.compile(r"(?:^|/)(?:ads?|banner|logo|avatar|gravatar)[-_/.]"
                      r"|jeg-empty|placeholder|spinner|/emoji/|/plugins/|/themes/|favicon|blank\.", re.I)
_SIZE_SEG = re.compile(r"-\d{2,4}x\d{2,4}(?=\.[A-Za-z0-9]+$)")


def _inst_tag():
    """本实例独有的短标记(重启就换一个)。旧卡片带着上一轮的批号进来时,
    一眼就能认出"这不是这一轮的队列",不用它去硬套位置。"""
    try:
        return "%04x%04x" % (int(time.time() * 1000) & 0xFFFF,
                             (os.getpid() ^ id(object())) & 0xFFFF)
    except Exception:
        return "0000"


def _clean(s):
    s = "" if s is None else str(s)
    s = re.sub(r"<[^>]+>", "", s)
    s = html_lib.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def _int(v, dft, lo, hi):
    try:
        n = int(float(str(v).strip()))
    except Exception:
        return dft
    return max(lo, min(hi, n))


def _hdr(headers, key):
    for k, v in (headers or {}).items():
        if k.lower() == key:
            return v
    return ""


def _stem_key(u):
    """去掉 WP 自动缩略图的尺寸段,用来判断两张图是不是同一张"""
    return _SIZE_SEG.sub("", urlparse(u).path)


def _has_size(u):
    return bool(_SIZE_SEG.search(urlparse(u).path))


# ==================================================================================
# 看图页(全屏 WebView):左右滑动切图 + 滑到底自动接下一组
#   · ###TITLE### 分类名  ###IDX### 起始第几张  ###COUNT### 起始总数
#   · 图片全由 Python 侧 ZAKA_APPEND 推进来,所以开头是空的(先显示「正在拉图 …」)
#   · 滑到倒数第 3 张就 console.log('ZAKA_MORE'),Java 侧收到去加载下一组再推回来
# ==================================================================================
# ==================================================================================
# 黑屏占位视频(320x180 · 4 小时 · 无声 · 8KB)—— 治客户端「正在切换站源」
#   图片线路本来就播不出来,客户端当它是坏源 → 自己去切源,屏幕就跳那句话。
#   给它一条真能播的(黑屏),播放器不报错,它就不切;看图窗本来就压在它上面。
# ==================================================================================
PH_MP4_B64 = "AAAAIGZ0eXBpc29tAAACAGlzb21pc28yYXZjMW1wNDEAAA51bW9vdgAAAGxtdmhkAAAAAAAAAAAAAAAAAAAD6ADbugAAAQAAAQAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAAABAAAAAAAAAAAAAAAAAABAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAgAADZ90cmFrAAAAXHRraGQAAAADAAAAAAAAAAAAAAABAAAAAADbugAAAAAAAAAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAAABAAAAAAAAAAAAAAAAAABAAAAAAUAAAAC0AAAAAAAkZWR0cwAAABxlbHN0AAAAAAAAAAEA27oAAB4AAAABAAAAAA0XbWRpYQAAACBtZGhkAAAAAAAAAAAAAAAAAABAAA4QAABVxAAAAAAALWhkbHIAAAAAAAAAAHZpZGUAAAAAAAAAAAAAAABWaWRlb0hhbmRsZXIAAAAMwm1pbmYAAAAUdm1oZAAAAAEAAAAAAAAAAAAAACRkaW5mAAAAHGRyZWYAAAAAAAAAAQAAAAx1cmwgAAAAAQAADIJzdGJsAAAAwnN0c2QAAAAAAAAAAQAAALJhdmMxAAAAAAAAAAEAAAAAAAAAAAAAAAAAAAAAAUAAtABIAAAASAAAAAAAAAABFUxhdmM2MC4zMS4xMDIgbGlieDI2NAAAAAAAAAAAAAAAGP//AAAAOGF2Y0MBZAAM/+EAGmdkAAys2YFBn58BEAAAAwPAAAADACDxQpmgAQAHaOl4GUsiwP34+AAAAAAQcGFzcAAAAAEAAAABAAAAFGJ0cnQAAAAAAAAAAgAAAAIAAAAYc3R0cwAAAAAAAAABAAAA8AAPAAAAAAAUc3RzcwAAAAAAAAABAAAAAQAAB4hjdHRzAAAAAAAAAO8AAAABAB4AAAAAAAEASwAAAAAAAQAeAAAAAAABAAAAAAAAAAEADwAAAAAAAQBLAAAAAAABAB4AAAAAAAEAAAAAAAAAAQAPAAAAAAABAEsAAAAAAAEAHgAAAAAAAQAAAAAAAAABAA8AAAAAAAEASwAAAAAAAQAeAAAAAAABAAAAAAAAAAEADwAAAAAAAQBLAAAAAAABAB4AAAAAAAEAAAAAAAAAAQAPAAAAAAABAEsAAAAAAAEAHgAAAAAAAQAAAAAAAAABAA8AAAAAAAEASwAAAAAAAQAeAAAAAAABAAAAAAAAAAEADwAAAAAAAQBLAAAAAAABAB4AAAAAAAEAAAAAAAAAAQAPAAAAAAABAEsAAAAAAAEAHgAAAAAAAQAAAAAAAAABAA8AAAAAAAEASwAAAAAAAQAeAAAAAAABAAAAAAAAAAEADwAAAAAAAQBLAAAAAAABAB4AAAAAAAEAAAAAAAAAAQAPAAAAAAABAEsAAAAAAAEAHgAAAAAAAQAAAAAAAAABAA8AAAAAAAEASwAAAAAAAQAeAAAAAAABAAAAAAAAAAEADwAAAAAAAQBLAAAAAAABAB4AAAAAAAEAAAAAAAAAAQAPAAAAAAABAEsAAAAAAAEAHgAAAAAAAQAAAAAAAAABAA8AAAAAAAEASwAAAAAAAQAeAAAAAAABAAAAAAAAAAEADwAAAAAAAQBLAAAAAAABAB4AAAAAAAEAAAAAAAAAAQAPAAAAAAABAEsAAAAAAAEAHgAAAAAAAQAAAAAAAAABAA8AAAAAAAEASwAAAAAAAQAeAAAAAAABAAAAAAAAAAEADwAAAAAAAQBLAAAAAAABAB4AAAAAAAEAAAAAAAAAAQAPAAAAAAABAEsAAAAAAAEAHgAAAAAAAQAAAAAAAAABAA8AAAAAAAEASwAAAAAAAQAeAAAAAAABAAAAAAAAAAEADwAAAAAAAQBLAAAAAAABAB4AAAAAAAEAAAAAAAAAAQAPAAAAAAABAEsAAAAAAAEAHgAAAAAAAQAAAAAAAAABAA8AAAAAAAEASwAAAAAAAQAeAAAAAAABAAAAAAAAAAEADwAAAAAAAQBLAAAAAAABAB4AAAAAAAEAAAAAAAAAAQAPAAAAAAABAEsAAAAAAAEAHgAAAAAAAQAAAAAAAAABAA8AAAAAAAEASwAAAAAAAQAeAAAAAAABAAAAAAAAAAEADwAAAAAAAQBLAAAAAAABAB4AAAAAAAEAAAAAAAAAAQAPAAAAAAABAEsAAAAAAAEAHgAAAAAAAQAAAAAAAAABAA8AAAAAAAEASwAAAAAAAQAeAAAAAAABAAAAAAAAAAEADwAAAAAAAQBLAAAAAAABAB4AAAAAAAEAAAAAAAAAAQAPAAAAAAABAEsAAAAAAAEAHgAAAAAAAQAAAAAAAAABAA8AAAAAAAEASwAAAAAAAQAeAAAAAAABAAAAAAAAAAEADwAAAAAAAQBLAAAAAAABAB4AAAAAAAEAAAAAAAAAAQAPAAAAAAABAEsAAAAAAAEAHgAAAAAAAQAAAAAAAAABAA8AAAAAAAEASwAAAAAAAQAeAAAAAAABAAAAAAAAAAEADwAAAAAAAQBLAAAAAAABAB4AAAAAAAEAAAAAAAAAAQAPAAAAAAABAEsAAAAAAAEAHgAAAAAAAQAAAAAAAAABAA8AAAAAAAEASwAAAAAAAQAeAAAAAAABAAAAAAAAAAEADwAAAAAAAQBLAAAAAAABAB4AAAAAAAEAAAAAAAAAAQAPAAAAAAABAEsAAAAAAAEAHgAAAAAAAQAAAAAAAAABAA8AAAAAAAEASwAAAAAAAQAeAAAAAAABAAAAAAAAAAEADwAAAAAAAQBLAAAAAAABAB4AAAAAAAEAAAAAAAAAAQAPAAAAAAABAEsAAAAAAAEAHgAAAAAAAQAAAAAAAAABAA8AAAAAAAEASwAAAAAAAQAeAAAAAAABAAAAAAAAAAEADwAAAAAAAQBLAAAAAAABAB4AAAAAAAEAAAAAAAAAAQAPAAAAAAABAEsAAAAAAAEAHgAAAAAAAQAAAAAAAAABAA8AAAAAAAEASwAAAAAAAQAeAAAAAAABAAAAAAAAAAEADwAAAAAAAQBLAAAAAAABAB4AAAAAAAEAAAAAAAAAAQAPAAAAAAABAEsAAAAAAAEAHgAAAAAAAQAAAAAAAAABAA8AAAAAAAEASwAAAAAAAQAeAAAAAAABAAAAAAAAAAEADwAAAAAAAQBLAAAAAAABAB4AAAAAAAEAAAAAAAAAAQAPAAAAAAABAEsAAAAAAAEAHgAAAAAAAQAAAAAAAAABAA8AAAAAAAEASwAAAAAAAQAeAAAAAAABAAAAAAAAAAEADwAAAAAAAQBLAAAAAAABAB4AAAAAAAEAAAAAAAAAAQAPAAAAAAABAEsAAAAAAAEAHgAAAAAAAQAAAAAAAAABAA8AAAAAAAEASwAAAAAAAQAeAAAAAAABAAAAAAAAAAEADwAAAAAAAQBLAAAAAAABAB4AAAAAAAEAAAAAAAAAAQAPAAAAAAABADwAAAAAAAIADwAAAAAAHHN0c2MAAAAAAAAAAQAAAAEAAADwAAAAAQAAA9RzdHN6AAAAAAAAAAAAAADwAAAC5gAAAA4AAAANAAAADQAAAA0AAAAUAAAADwAAAA4AAAANAAAAFAAAABAAAAAOAAAADQAAABQAAAAQAAAADgAAAA0AAAAUAAAAEAAAAA4AAAANAAAAFAAAABAAAAAOAAAADQAAABQAAAAQAAAADgAAAA0AAAAUAAAAEAAAAA4AAAANAAAAFAAAABAAAAAOAAAADQAAABQAAAAQAAAADgAAAA0AAAAUAAAAEAAAAA4AAAANAAAAFAAAABAAAAAOAAAADQAAABQAAAAQAAAADgAAAA0AAAAUAAAAEAAAAA4AAAANAAAAFAAAABAAAAAOAAAADQAAABQAAAAQAAAADgAAAA0AAAAUAAAAEAAAAA4AAAANAAAAFAAAABAAAAAOAAAADQAAABQAAAAQAAAADgAAAA0AAAAUAAAAEAAAAA4AAAANAAAAFAAAABAAAAAOAAAADQAAABQAAAAQAAAADgAAAA0AAAAUAAAAEAAAAA4AAAANAAAAFAAAABAAAAAOAAAADQAAABQAAAAQAAAADgAAAA0AAAAUAAAAEAAAAA4AAAANAAAAFAAAABAAAAAOAAAADQAAABQAAAAQAAAADgAAAA0AAAAUAAAAEAAAAA4AAAANAAAAFAAAABAAAAAOAAAADQAAABQAAAAQAAAADgAAAA0AAAAUAAAAEAAAAA4AAAANAAAAFAAAABAAAAAOAAAADQAAABQAAAAQAAAADgAAAA0AAAAUAAAAEAAAAA4AAAANAAAAFAAAABAAAAAOAAAADQAAABQAAAAQAAAADgAAAA0AAAAUAAAAEAAAAA4AAAANAAAAFAAAABAAAAAOAAAADQAAABQAAAAQAAAADgAAAA0AAAAUAAAAEAAAAA4AAAANAAAAFAAAABAAAAAOAAAADQAAABQAAAAQAAAADgAAAA0AAAAUAAAAEAAAAA4AAAANAAAAFAAAABAAAAAOAAAADQAAABQAAAAQAAAADgAAAA0AAAAUAAAAEAAAAA4AAAANAAAAFAAAABAAAAAOAAAADQAAABQAAAAQAAAADgAAAA0AAAAUAAAAEAAAAA4AAAANAAAAFAAAABAAAAAOAAAADQAAABQAAAAQAAAADgAAAA0AAAAUAAAAEAAAAA4AAAANAAAAFAAAABAAAAAOAAAADQAAABQAAAAQAAAADgAAAA0AAAAUAAAAEAAAAA4AAAANAAAAFAAAABAAAAAOAAAADQAAABQAAAAQAAAADgAAAA0AAAAUAAAAEAAAAA4AAAANAAAAEwAAABAAAAANAAAAFHN0Y28AAAAAAAAAAQAADqUAAABidWR0YQAAAFptZXRhAAAAAAAAACFoZGxyAAAAAAAAAABtZGlyYXBwbAAAAAAAAAAAAAAAAC1pbHN0AAAAJal0b28AAAAdZGF0YQAAAAEAAAAATGF2ZjYwLjE2LjEwMAAAAAhmcmVlAAARmG1kYXQAAAKtBgX//6ncRem95tlIt5Ys2CDZI+7veDI2NCAtIGNvcmUgMTY0IHIzMTA4IDMxZTE5ZjkgLSBILjI2NC9NUEVHLTQgQVZDIGNvZGVjIC0gQ29weWxlZnQgMjAwMy0yMDIzIC0gaHR0cDovL3d3dy52aWRlb2xhbi5vcmcveDI2NC5odG1sIC0gb3B0aW9uczogY2FiYWM9MSByZWY9NSBkZWJsb2NrPTE6MDowIGFuYWx5c2U9MHgzOjB4MTEzIG1lPWhleCBzdWJtZT04IHBzeT0xIHBzeV9yZD0xLjAwOjAuMDAgbWl4ZWRfcmVmPTEgbWVfcmFuZ2U9MTYgY2hyb21hX21lPTEgdHJlbGxpcz0yIDh4OGRjdD0xIGNxbT0wIGRlYWR6b25lPTIxLDExIGZhc3RfcHNraXA9MSBjaHJvbWFfcXBfb2Zmc2V0PS0yIHRocmVhZHM9NiBsb29rYWhlYWRfdGhyZWFkcz0xIHNsaWNlZF90aHJlYWRzPTAgbnI9MCBkZWNpbWF0ZT0xIGludGVybGFjZWQ9MCBibHVyYXlfY29tcGF0PTAgY29uc3RyYWluZWRfaW50cmE9MCBiZnJhbWVzPTMgYl9weXJhbWlkPTIgYl9hZGFwdD0xIGJfYmlhcz0wIGRpcmVjdD0zIHdlaWdodGI9MSBvcGVuX2dvcD0wIHdlaWdodHA9MiBrZXlpbnQ9MjUwIGtleWludF9taW49MSBzY2VuZWN1dD00MCBpbnRyYV9yZWZyZXNoPTAgcmNfbG9va2FoZWFkPTUwIHJjPWNyZiBtYnRyZWU9MSBjcmY9NTEuMCBxY29tcD0wLjYwIHFwbWluPTAgcXBtYXg9NjkgcXBzdGVwPTQgaXBfcmF0aW89MS40MCBhcT0xOjEuMDAAgAAAADFliIQAGf/+wHeBS0SP4+ObJStOHUyNgPdAAC3fjsqfMYOiSAI0AAFHG9lpDSnEZK9BAAAACkGaJGxB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"
# v2.5:占位片的回环服务 + 缓存目录,整个进程共享一份(不按实例重复起)
_PH_LOCK = threading.Lock()
_PH_SRV = {"srv": None, "url": ""}
_PH_DIR_CACHE = [""]
PH_NAME = "zaka_ph.mp4"
PH_SIZE = 8245

VIEW_NAMES = ["\u2194 \u5de6\u53f3", "\u2195 \u4e0a\u4e0b", "\u25a6 \u7011\u5e03\u6d41"]
VIEW_TIPS = ["\u5de6\u53f3\u6ed1\u52a8\u5207\u6362 \u00b7 \u5355\u51fb\u653e\u5927 \u00b7 \u53cc\u51fb\u8fd8\u539f \u00b7 \u6ed1\u5230\u6700\u540e\u81ea\u52a8\u52a0\u8f7d\u4e0b\u4e00\u7ec4",
             "\u4e0a\u4e0b\u65e0\u7f1d\u770b\u56fe \u00b7 \u56fe\u7247\u6ee1\u5bbd\u81ea\u9002\u5e94 \u00b7 \u6ed1\u5230\u5e95\u81ea\u52a8\u52a0\u8f7d\u4e0b\u4e00\u7ec4",
             "\u7011\u5e03\u6d41\u770b\u56fe \u00b7 \u56fe\u7247\u6ee1\u5bbd\u81ea\u9002\u5e94 \u00b7 \u6ed1\u5230\u5e95\u81ea\u52a8\u52a0\u8f7d\u4e0b\u4e00\u7ec4"]


GALLERY_HTML = """<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<meta name="referrer" content="no-referrer">
<style>
html,body{margin:0;height:100%;background:#000;color:#eee;font-family:sans-serif;overflow:hidden;
 -webkit-user-select:none;user-select:none}
.bar{position:fixed;top:0;left:0;right:0;z-index:20;padding:9px 12px;font-size:14px;
 background:linear-gradient(rgba(0,0,0,.82),rgba(0,0,0,0));display:flex;align-items:center;gap:10px}
.bar .ttl{flex:1 1 auto;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.bar .who{flex:0 0 auto;max-width:38%;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
 text-align:right;color:#ff5c8a;font-weight:600;text-shadow:0 1px 4px rgba(0,0,0,.9)}
.bar .mode{flex:0 0 auto;padding:6px 13px;border-radius:999px;background:rgba(255,255,255,.16);
 border:1px solid rgba(255,255,255,.42);font-size:13px;color:#fff;white-space:nowrap}
#stage{position:absolute;top:0;left:0;right:0;bottom:0;background:#000}
.pages{position:absolute;top:0;left:0;right:0;bottom:0;display:flex;overflow-x:auto;overflow-y:hidden;
 scroll-snap-type:x mandatory;-webkit-overflow-scrolling:touch;scrollbar-width:none}
.pages::-webkit-scrollbar{display:none}
.page{flex:0 0 100%;width:100%;height:100%;display:flex;align-items:center;justify-content:center;
 overflow:hidden;scroll-snap-align:center;scroll-snap-stop:always}
.page img{max-width:100%;max-height:100%;object-fit:contain;transition:transform .16s ease-out}
.page img.zoom{transform:scale(2.4)}
.vbox,.mbox{position:absolute;top:0;left:0;right:0;bottom:0;display:none;background:#000;
 overflow-y:auto;overflow-x:hidden;-webkit-overflow-scrolling:touch;scrollbar-width:none}
.vbox::-webkit-scrollbar,.mbox::-webkit-scrollbar{display:none}
.mbox{gap:3px;padding:0 2px;box-sizing:border-box}
.mcol{flex:1 1 0;min-width:0}
.vitem,.witem{width:100%;line-height:0}
.witem{margin-bottom:3px}
.vitem img,.witem img{width:100%;height:auto;display:block}
.fail{color:#666;font-size:13px;text-align:center;padding:26px 0;line-height:1.5;background:#000}
.boot{position:fixed;left:0;right:0;top:50%;transform:translateY(-50%);text-align:center;
 color:#8a8a8a;font-size:15px;z-index:25}
.counter{position:fixed;left:50%;bottom:16px;transform:translateX(-50%);background:rgba(0,0,0,.62);
 padding:6px 14px;border-radius:999px;font-size:13px;z-index:30;white-space:nowrap;color:#eee}
.tip{position:fixed;bottom:50px;left:0;right:0;color:#7d7d7d;font-size:12px;z-index:30;
 text-align:center;padding:0 16px;line-height:1.5}
.msw{position:fixed;left:10px;bottom:14px;z-index:31;display:flex;gap:6px;opacity:.78}
.msw b{padding:7px 11px;border-radius:999px;background:rgba(0,0,0,.62);
 border:1px solid rgba(255,255,255,.36);color:#dcdcdc;font-size:12px;font-weight:400;
 white-space:nowrap}
.msw b.on{background:#ff5c8a;border-color:#ff5c8a;color:#fff;font-weight:700;opacity:1}
</style></head><body>
<div class="bar"><span class="ttl">###TITLE###</span><span class="who" id="who"></span>
<span class="mode" id="modebtn">###MODENAME###</span></div>
<div id="stage">
 <div class="pages" id="pages"></div>
 <div class="vbox" id="vbox"></div>
 <div class="mbox" id="mbox"></div>
</div>
<div class="boot" id="boot">正在拉图 …</div>
<div class="counter" id="counter">###COUNTER###</div>
<div class="tip" id="tip">###TIP###</div>
<div class="msw" id="msw"><b data-m="0">\u2194 \u5de6\u53f3</b><b data-m="1">\u2195 \u4e0a\u4e0b</b><b data-m="2">\u25a6 \u7011\u5e03</b></div>
<script type="application/json" id="zfirst">###MEDIA###</script>
<script>
var MODES=['↔ 左右','↕ 上下','▦ 瀑布流'];
var TIPS=['左右滑动切换 · 单击放大 · 双击还原 · 滑到最后自动加载下一组',
          '上下无缝看图 · 图片满宽自适应 · 滑到底自动加载下一组',
          '瀑布流看图 · 图片满宽自适应 · 滑到底自动加载下一组'];
var MODE=###MODE###,idx=###IDX###,n=###COUNT###;
var items=[],nodes=[],cols=[],ch=[],DEFH=1.38;
var ended=false,busy=false,lastAsk=0,st=null;
var pages=document.getElementById('pages'),vbox=document.getElementById('vbox'),mbox=document.getElementById('mbox');
function q(id){return document.getElementById(id)}
function cur(){return MODE===0?pages:(MODE===1?vbox:mbox)}
function boot(off){var b=q('boot');if(b){b.style.display=off?'none':'block'}}
function setTip(t){var e=q('tip');if(e){e.textContent=t||TIPS[MODE]||''}}
function updChip(){
  var e=q('modebtn');if(e){e.textContent=MODES[MODE]||''}
  var w=q('msw');
  if(w){
    var bs=w.getElementsByTagName('b');
    for(var i=0;i<bs.length;i++){
      var m=parseInt(bs[i].getAttribute('data-m'),10);
      bs[i].className=(m===MODE)?'on':'';
    }
  }
}
function upd(){
  var c=q('counter');
  var tot=items.length;
  if(c){c.textContent=tot>0?((Math.min(idx,tot-1)+1)+' / '+tot):'…'}
  var wb=q('who');
  if(wb){var it=items[idx];wb.textContent=(it&&it.w)?it.w:''}
  try{document.title='IDX'+idx}catch(e){}
  try{var cu=items[idx];if(cu&&cu.u){console.log('ZAKA_CUR:'+cu.u)}}catch(e){}
  nearEnd();
}
function askMore(){
  if(ended){return}
  var t=Date.now();
  if(busy||(t-lastAsk)<1200){return}
  lastAsk=t;busy=true;setTip('正在加载下一组 …');
  try{console.log('ZAKA_MORE')}catch(e){}
  setTimeout(function(){if(busy){busy=false;setTip('没自动接上就点右下角「继续加载」')}},3000);
}
function nearEnd(){
  var tot=items.length;
  if(tot<=0){return}
  var go=false;
  if(MODE===0){go=idx>=tot-3}
  else{var b=cur();if(b){go=(b.scrollHeight-b.scrollTop-b.clientHeight)<=b.clientHeight*0.9}}
  if(go){askMore()}
}
function failNode(){var f=document.createElement('div');f.className='fail';f.style.display='none';f.textContent='加载失败';return f}
function mkImg(it){
  var im=document.createElement('img');
  im.setAttribute('data-chain',it.c||'');
  im.setAttribute('data-i','0');
  im.onerror=function(){
    var i=parseInt(im.getAttribute('data-i')||'0',10);
    var cn=(im.getAttribute('data-chain')||'').split('|').filter(function(s){return s});
    if(i<cn.length){im.setAttribute('data-i',String(i+1));setTimeout(function(){im.src=cn[i]},200);}
    else{im.onerror=null;im.style.display='none';var p=im.parentNode;var f=p?p.querySelector('.fail'):null;if(f){f.style.display='block'}}
  };
  im.onload=function(){try{if(im.naturalWidth>0){it.r=im.naturalHeight/im.naturalWidth}}catch(e){}};
  im.setAttribute('data-src',it.u||'');
  return im;
}
function showK(k){
  var it=items[k],el=nodes[k];
  if(!it||!el){return}
  if(!el.getAttribute('src')){el.src=it.u||''}
}
function lazyScan(){
  if(items.length<=0){return}
  if(MODE===0){for(var k=idx-1;k<=idx+2;k++){if(k>=0&&k<items.length){showK(k)}}return}
  var b=cur();
  if(!b){return}
  var lim=b.scrollTop+b.clientHeight*1.8;
  for(var i=0;i<nodes.length;i++){
    var el=nodes[i];
    if(!el||el.getAttribute('src')){continue}
    if(el.offsetTop<=lim){showK(i)}
  }
}
function addNode(i){
  var it=items[i];
  if(MODE===0){
    var d0=document.createElement('div');d0.className='page';d0.setAttribute('data-who',it.w||'');
    var im0=mkImg(it);d0.appendChild(im0);d0.appendChild(failNode());
    pages.appendChild(d0);nodes[i]=im0;
    return;
  }
  if(MODE===1){
    var d1=document.createElement('div');d1.className='vitem';
    var im1=mkImg(it);d1.appendChild(im1);d1.appendChild(failNode());
    vbox.appendChild(d1);nodes[i]=im1;
    return;
  }
  var k2=0;
  for(var j=1;j<cols.length;j++){if(ch[j]<ch[k2]){k2=j}}
  var d2=document.createElement('div');d2.className='witem';
  var im2=mkImg(it);d2.appendChild(im2);d2.appendChild(failNode());
  cols[k2].appendChild(d2);nodes[i]=im2;
  ch[k2]+=(mbox.clientWidth/Math.max(1,cols.length))*(it.r||DEFH)+3;
}
function render(){
  pages.innerHTML='';vbox.innerHTML='';mbox.innerHTML='';
  nodes=[];cols=[];ch=[];
  pages.style.display=(MODE===0)?'flex':'none';
  vbox.style.display=(MODE===1)?'block':'none';
  mbox.style.display=(MODE===2)?'flex':'none';
  if(MODE===2){
    var need=(mbox.clientWidth>=560)?3:2;
    for(var c=0;c<need;c++){var col=document.createElement('div');col.className='mcol';mbox.appendChild(col);cols.push(col);ch.push(0)}
  }
  for(var i=0;i<items.length;i++){addNode(i)}
  lazyScan();upd();
}
function nearest(){
  var b=cur();
  if(!b){return 0}
  var top=b.scrollTop,best=0,bd=1e18;
  for(var i=0;i<nodes.length;i++){
    var el=nodes[i];
    if(!el){continue}
    var d=Math.abs(el.offsetTop-top);
    if(d<bd){bd=d;best=i}
  }
  return best;
}
function go(i,anim){
  var tot=items.length;
  if(tot<=0){return}
  idx=Math.max(0,Math.min(tot-1,i||0));
  var x=idx*pages.clientWidth;
  if(anim===false){pages.scrollLeft=x}
  else{try{pages.scrollTo({left:x,behavior:'smooth'})}catch(e){pages.scrollLeft=x}}
  upd();lazyScan();
}
function place(k){
  var tot=items.length;
  if(tot<=0){return}
  idx=Math.max(0,Math.min(tot-1,k||0));
  if(MODE===0){go(idx,false);return}
  var b=cur(),el=nodes[idx];
  if(b&&el){b.scrollTop=Math.max(0,el.offsetTop-8)}
  upd();lazyScan();
}
window.ZAKA_MODE=function(v){
  var nv;
  if(v===undefined||v===null||v===''){nv=(MODE+1)%3}
  else{nv=parseInt(v,10);if(isNaN(nv)){nv=(MODE+1)%3}}
  nv=((nv%3)+3)%3;
  var k=(items.length>0)?((MODE===0)?idx:nearest()):0;
  MODE=nv;
  render();place(k);updChip();setTip('');lazyScan();
  try{console.log('ZAKA_SETMODE:'+MODE)}catch(e){}
  return MODE;
};
window.ZAKA_APPEND=function(list){
  if(!list||!list.length){return}
  boot(true);
  var start=items.length;
  for(var i=0;i<list.length;i++){
    var it=list[i]||{};
    items.push({u:it.u||'',c:it.c||'',w:it.w||'',r:0});
  }
  for(var k=start;k<items.length;k++){addNode(k)}
  busy=false;setTip('');lazyScan();upd();
};
window.ZAKA_RESET=function(list,title){
  items=[];nodes=[];cols=[];ch=[];ended=false;busy=false;lastAsk=0;idx=0;n=0;
  try{var t=document.querySelector('.bar .ttl');if(t&&title){t.textContent=title}}catch(e){}
  render();boot(true);setTip('');
  window.ZAKA_APPEND(list||[]);
  if(MODE===0){go(0,false)}else{var b=cur();if(b){b.scrollTop=0}lazyScan()}
  upd();
  return true;
};
window.ZAKA_END=function(msg){ended=true;busy=true;boot(true);setTip(msg||'已经到底了')};
window.ZAKA_INFO=function(msg){setTip(msg)};
pages.addEventListener('scroll',function(){
  if(st){clearTimeout(st)}
  st=setTimeout(function(){
    if(MODE!==0){return}
    var i=Math.round(pages.scrollLeft/Math.max(1,pages.clientWidth));
    idx=Math.max(0,Math.min(items.length-1,i));
    upd();lazyScan();
  },110);
},false);
vbox.addEventListener('scroll',function(){
  if(st){clearTimeout(st)}
  st=setTimeout(function(){
    if(MODE!==1){return}
    var k=nearest();
    if(k!==idx){idx=k}
    upd();lazyScan();
  },110);
},false);
mbox.addEventListener('scroll',function(){
  if(st){clearTimeout(st)}
  st=setTimeout(function(){
    if(MODE!==2){return}
    var k=nearest();
    if(k!==idx){idx=k}
    upd();lazyScan();
  },110);
},false);
pages.addEventListener('click',function(ev){
  if(MODE!==0){return}
  var t=ev.target;
  if(t&&t.tagName==='IMG'){t.classList.toggle('zoom')}
},false);
var modeBtnElement=document.getElementById('modebtn');
if(modeBtnElement){modeBtnElement.addEventListener('click',function(){window.ZAKA_MODE()},false)}
(function(){
  var w=document.getElementById('msw');
  if(!w){return}
  w.addEventListener('click',function(ev){
    var t=ev.target||ev.srcElement,mm=-1;
    while(t&&t!==w){
      if(t.getAttribute&&t.getAttribute('data-m')!==null){mm=parseInt(t.getAttribute('data-m'),10);break}
      t=t.parentNode;
    }
    if(mm>=0){window.ZAKA_MODE(mm)}
  },false);
})();
document.addEventListener('keydown',function(e){
  var k=e.keyCode;
  if(k===39||k===40||k===32){if(MODE===0){go(idx+1)}else{var b=cur();b.scrollTop=b.scrollTop+b.clientHeight*0.9}}
  else if(k===37||k===38){if(MODE===0){go(idx-1)}else{var b2=cur();b2.scrollTop=Math.max(0,b2.scrollTop-b2.clientHeight*0.9)}}
  else if(k===13){window.ZAKA_MODE()}
},false);
window.addEventListener('resize',function(){
  if(MODE===0){go(idx,false)}
  else{var k=idx;render();place(k)}
},false);
(function(){
  var first=[];
  try{first=JSON.parse((document.getElementById('zfirst')||{}).textContent||'[]')||[]}catch(e){first=[]}
  for(var i=0;i<first.length;i++){
    var it=first[i]||{};
    items.push({u:it.u||'',c:it.c||'',w:it.w||'',r:0});
  }
  if(items.length>n){n=items.length}
  boot(items.length>0);
  render();updChip();setTip('');
  if(MODE===0){go(idx,false)}else{lazyScan()}
})();
</script></body></html>
"""


class Spider(BaseSpider):

    def __init__(self):
        self.per = 30                   # 每页卡片数
        self.timeout = 20
        self.sort = "date"
        self.hot_default = "month"
        self.ttl = 0                    # 列表:0=每次现拉(不吃缓存)
        self.cache = 0                  # 图集/看图:0=现拉(默认) 1=吃缓存
        self.subpage = 2                # 小分类聚合页数
        self.line = 1                   # 1=详情层带「🖼 查看图片」线路(照 Pinterest·默认) 0=不给
        self.subnav = 1                 # 1=大分类先列小分类(两级) 0=大分类直接出图墙
        self.view_mode = 0              # 看图页模式 0=左右 1=上下无缝 2=瀑布流(在看图页能实时切)
        self.ph = 1                     # 1=图片线路回一条**真能播**的黑屏占位片(默认·根治切站源)
                                        # 0=照 Pinterest 回 about:blank(个别客户端会判坏源去切站源)
        self.auto = 2                   # 详情页兜底弹窗 2=端口没自动弹才补(默认) 1=立刻弹 0=不补
        self._ph_lock = threading.Lock()
        self._ph_srv = None             # 本机小服务:把占位片用 http://127.0.0.1 发出去
        self._ph_srv_url = ""           # 起好之后复用,不重复起
        self._sess = None
        self._cache = {}                # key -> (ts, (text, headers))
        self._lock = threading.RLock()
        self._gap_lock = threading.Lock()
        self._last_req = [0.0]
        self._cat_cache = None          # [(id, slug, name, count)]
        self._sub_cache = {}            # slug -> (ts, [子分类])
        self._prefetching = set()       # 正在后台预取下一列作品的 key
        self._warmed = False            # 小分类预热标记
        self._queues = {}               # 看图队列
        self._qserial = 0
        self._tag = _inst_tag()         # 本实例独有标记(旧卡片一眼认出)
        self._cur_url = ""              # 看图页正显示的那张图(页面回报,下载用)
        self._pop_js = None             # 窗开着时,原地换内容的入口
        self._vm = None                 # 当前活跃的看图队列
        self._cur_idx = 0               # 看图页当前第几张(页面标题回传)
        self._popup_host = None
        self._pop_lock = threading.Lock()
        self._pop_busy = 0.0            # 正在开窗(防同一瞬间弹两次)
        self._pop_alive = False         # 看图窗现在开着没
        self._pop_key = ""              # 开着的是哪一条看图流

    # ==================== 初始化 / 配置 ====================

    def getName(self):
        return "XiuRen"

    def init(self, extend=""):
        cfg = {}
        ext = _clean(extend)
        if ext:
            try:
                j = json.loads(ext)
                if isinstance(j, dict):
                    cfg = j
            except Exception:
                cfg = {}
            if not cfg:
                if "=" in ext:
                    for kv in re.split(r"[&,;\s]+", ext):
                        if "=" in kv:
                            k, v = kv.split("=", 1)
                            cfg[_clean(k).lower()] = _clean(v)
                elif re.match(r"^\d+$", ext):
                    cfg["per"] = ext
        self.per = _int(cfg.get("per"), 30, 10, 100)
        self.timeout = _int(cfg.get("timeout"), 20, 5, 60)
        self.sort = _clean(cfg.get("sort")).lower() or "date"
        if self.sort not in ("date", "modified", "title"):
            self.sort = "date"
        hot = _clean(cfg.get("hot")).lower()
        self.hot_default = hot if hot in HOT_PATH else "month"
        self.ttl = _int(cfg.get("ttl"), 0, 0, 3600)
        self.cache = _int(cfg.get("cache"), 0, 0, 1)
        self.subpage = _int(cfg.get("subpage"), 2, 1, 6)
        self.subnav = _int(cfg.get("sub"), 1, 0, 1)
        self.line = _int(cfg.get("line"), 1, 0, 1)
        self.ph = _int(cfg.get("ph"), 1, 0, 1)
        self.auto = _int(cfg.get("auto"), 2, 0, 2)
        # 0=默认,用 base.spider 图文源契约的 pics:// 播放串(主流 TVBox/影视仓通用)
        # 1=旧版私有 WebView 桥(需客户端支持 ZAKA_APPEND 等能力,兼容性差)
        self.webview = _int(cfg.get("webview"), 0, 0, 1)
        vm = _clean(cfg.get("view")).lower()
        if vm in ("h", "v", "w"):
            self.view_mode = {"h": 0, "v": 1, "w": 2}[vm]
        elif vm != "":
            self.view_mode = _int(vm, self.view_mode, 0, 2)
        else:
            self._load_mode()
        self._new_session()
        return self

    def _new_session(self):
        if requests is None:
            self._sess = None
            return
        s = requests.Session()
        s.headers.update({
            "User-Agent": UA,
            "Accept": "application/json,text/html,application/xhtml+xml,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": SITE + "/",
        })
        self._sess = s

    # ==================== 网络层(缓存 + 限速 + 重试) ====================

    def _throttle(self):
        with self._gap_lock:
            d = time.time() - self._last_req[0]
            if d < REQ_GAP:
                time.sleep(REQ_GAP - d)
            self._last_req[0] = time.time()

    def _fetch(self, url, params=None, ttl=None):
        """返回 (文本, 响应头)。带内存缓存,拿不到就返回 (None, {})"""
        p = dict((k, v) for k, v in (params or {}).items() if v not in (None, ""))
        key = url + ("?" + urlencode(sorted(p.items())) if p else "")
        ttl = LIST_TTL if ttl is None else ttl
        now = time.time()
        with self._lock:
            hit = self._cache.get(key)
            if hit and ttl > 0 and now - hit[0] < ttl:
                return hit[1]
        if self._sess is None:
            return self._fetch_urllib(key)      # key 里已经拼好了参数,别用裸 url
        txt, hd = None, {}
        for i in range(3):
            try:
                self._throttle()
                r = self._sess.get(url, params=p or None, timeout=self.timeout)
                if r.status_code == 200 and r.text:
                    txt, hd = r.text, dict(r.headers)
                    break
                if r.status_code in (400, 404):
                    break               # 真没有,别重试
            except Exception:
                pass
            time.sleep(0.35 * (i + 1))
        if txt is None:
            return None, {}
        with self._lock:
            self._cache[key] = (time.time(), (txt, hd))
            if len(self._cache) > 260:
                for k in sorted(self._cache, key=lambda x: self._cache[x][0])[:80]:
                    self._cache.pop(k, None)
        return txt, hd

    def _fetch_urllib(self, url):
        """没装 requests 的环境(纯 py 引擎)也能跑"""
        try:
            import urllib.request as _ur
            req = _ur.Request(url, headers={"User-Agent": UA,
                                            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                                            "Referer": SITE + "/"})
            self._throttle()
            r = _ur.urlopen(req, timeout=self.timeout)
            txt = r.read().decode("utf-8", "ignore")
            hd = dict(r.headers)
            with self._lock:
                self._cache[url] = (time.time(), (txt, hd))
            return txt, hd
        except Exception:
            return None, {}

    def _json(self, url, params=None, ttl=None):
        txt, hd = self._fetch(url, params, ttl)
        if not txt:
            return None, {}
        try:
            return json.loads(txt), hd
        except Exception:
            return None, hd

    # ==================== 基础数据 ====================

    def _cats(self):
        """站点大分类表 (id, slug, 名称, 作品数),按作品数倒序"""
        with self._lock:
            if self._cat_cache:
                return self._cat_cache
        data, _ = self._json(API + "/categories",
                             {"per_page": 100, "orderby": "count", "order": "desc",
                              "_fields": "id,name,slug,count"}, ttl=CACHE_CAT)
        out = []
        if isinstance(data, list):
            for c in data:
                if not isinstance(c, dict):
                    continue
                slug = _clean(c.get("slug"))
                name = _clean(c.get("name"))
                cnt = c.get("count") or 0
                if not slug or slug in ("uncategorized",):
                    continue
                if cnt and int(cnt) <= 0:
                    continue
                out.append((_int(c.get("id"), 0, 0, 10 ** 9), slug, name or slug, int(cnt or 0)))
        if not out:
            out = [(0, s, n, 0) for s, n in CATS_FALLBACK]
        with self._lock:
            self._cat_cache = out
        return out

    def _cat_key(self, key):
        """分类入口可能是 ID,也可能是 slug;统一成接口认的 ID 字符串"""
        key = _clean(key)
        if not key:
            return ""
        if key.isdigit():
            return key
        for cid, slug, _n, _c in self._cats():
            if slug == key:
                return str(cid) if cid else ""
        return ""

    def _cat_name(self, key):
        key = _clean(key)
        for cid, slug, name, _c in self._cats():
            if key == str(cid) or key == slug:
                return name
        return key

    def _featured(self, p, big=False):
        """文章封面。JNews 的 featured_media 只给 800x445 的裁切版,
        这里优先用接口里最大的那档,拿不到就用 source_url"""
        em = p.get("_embedded") if isinstance(p.get("_embedded"), dict) else {}
        fm = em.get("wp:featuredmedia")
        if isinstance(fm, list) and fm:
            f = fm[0] if isinstance(fm[0], dict) else {}
            src = _clean(f.get("source_url"))
            if src:
                return src
            md = f.get("media_details") if isinstance(f.get("media_details"), dict) else {}
            sizes = md.get("sizes") if isinstance(md.get("sizes"), dict) else {}
            best = ""
            for k in ("full", "large", "medium_large", "medium"):
                s = sizes.get(k) if isinstance(sizes.get(k), dict) else None
                if s and _clean(s.get("source_url")):
                    best = _clean(s.get("source_url"))
                    break
            if best:
                return best
        return ""

    def _card(self, p, tag=""):
        """列表卡片。vod_id 里带上队列标记,点一下直接进看图页"""
        pid = str(p.get("id") or "")
        t = p.get("title")
        title = _clean(t.get("rendered") if isinstance(t, dict) else t)
        date = _clean(p.get("date") or "")[:10]
        return {
            "vod_id": "p:" + pid,
            "vod_name": title or ("作品 " + pid),
            "vod_pic": self._featured(p),
            "vod_remarks": date or tag,
            "vod_actor": "",
            "vod_content": "",
        }

    # ==================== 列表:API 分页 ====================

    def _list_posts(self, pg, cat=None, orderby="date", search=None, tag=None):
        params = {
            "_fields": "id,link,title,date,featured_media,_links,_embedded",
            "_embed": "wp:featuredmedia",
            "per_page": self.per,
            "page": pg,
            "orderby": orderby,
            "order": "asc" if orderby == "title" else "desc",
        }
        if cat:
            params["categories"] = cat
        if tag:
            params["tags"] = tag
        if search:
            params["search"] = search
        data, hd = self._json(API + "/posts", params, ttl=self.ttl)
        posts = data if isinstance(data, list) else []
        total_pages = _int(_hdr(hd, "x-wp-totalpages"), 1, 1, 100000)
        total = _int(_hdr(hd, "x-wp-total"), len(posts), 0, 10000000)
        return posts, total_pages, total

    def _list_posts_paged(self, pg, cat=None, orderby="date", search=None, tag=None):
        """接口第一页就是空(有可能 page 超界)→ 退回第 1 页,别给用户一片空白"""
        posts, pages, total = self._list_posts(pg, cat, orderby, search, tag)
        if posts:
            return posts, pages, total
        if pg > 1:
            if total and pg > pages:
                return [], pages, total
            posts, pages, total = self._list_posts(1, cat, orderby, search, tag)
        return posts, pages, total

    def _page(self, items, pg, pagecount, total=None):
        return {
            "list": items,
            "page": pg,
            "pagecount": max(1, pagecount),
            "limit": len(items),
            "total": total if total is not None else len(items),
            "parse": 0,
            "jx": 0,
        }

    # ==================== 列表:榜单页(HTML) ====================

    def _hot_cards(self, key, pg):
        path = HOT_PATH.get(key) or HOT_PATH["month"]
        url = SITE + path
        if pg > 1:
            url = url.rstrip("/") + "/page/%d/" % pg
        txt, _ = self._fetch(url, ttl=HOT_TTL)
        if not txt:
            return [], pg
        host = urlparse(SITE).netloc
        arts = re.findall(r"<article[^>]*class=\"[^\"]*jeg_post[^\"]*\"[^>]*>(.*?)</article>",
                          txt, re.S)
        items, seen = [], set()
        for a in arts:
            link = ""
            for m in re.finditer(r'href="([^"]+)"', a):
                u = html_lib.unescape(m.group(1))
                if not u.startswith("http"):
                    u = urljoin(SITE + "/", u)
                if host not in u:
                    continue
                low = u.lower()
                if any(x in low for x in ("/category/", "/tag/", "/page/", "/author/",
                                          "/wp-content/", "/wp-json", "/?s=", "/feed")):
                    continue
                link = u
                break
            if not link or link in seen:
                continue
            seen.add(link)
            pic = ""
            im = re.search(r'<img[^>]+(?:data-src|data-lazy-src|src)="([^"]+)"', a, re.I)
            if im and self._img_ok(im.group(1)):
                pic = urljoin(SITE + "/", im.group(1))
            t = re.search(r'class="jeg_post_title"[^>]*>\s*<a[^>]*>(.*?)</a>', a, re.S)
            if not t:
                t = re.search(r'aria-label="(?:Read article:\s*)?([^"]+)"', a)
            title = _clean(t.group(1)) if t else ""
            if not title:
                title = urlparse(link).path.strip("/").split("/")[-1]
            items.append({
                "vod_id": "u:" + link,
                "vod_name": title,
                "vod_pic": pic,
                "vod_remarks": HOT_NAME.get(key, "热门")[2:] if len(HOT_NAME.get(key, "")) > 2 else "热门",
                "vod_actor": "",
                "vod_content": "",
            })
        total_found = len(items)
        items = items[:self.per]            # 榜页一页给 90 个,别一次全铺上去
        pagecount = pg + 1 if total_found >= 8 else pg
        return items, pagecount

    # ==================== 小分类(大分类下的标签聚合) ====================

    def _subcats(self, catkey):
        """某个大分类下的「小分类」= 这个分类里反复出现的标签(模特 / 角色 / 作品)。
        做法:并发拉这个分类最近 subpage 页文章,统计标签出现次数,再一次性换名字和封面。
        结果缓存 1 小时,第二次点进来是秒开的。"""
        cid = self._cat_key(catkey)
        if not cid:
            return []
        ck = str(cid)
        with self._lock:
            hit = self._sub_cache.get(ck)
            if hit and time.time() - hit[0] < CACHE_SUB:
                return hit[1]

        cnt = {}
        cover = {}
        lock = threading.Lock()

        def work(pg):
            data, _hd = self._json(API + "/posts",
                                   {"categories": cid, "per_page": 100, "page": pg,
                                    "_embed": "wp:featuredmedia",
                                    "_fields": "id,featured_media,tags,_links,_embedded"},
                                   ttl=CACHE_DETAIL)
            if not isinstance(data, list):
                return
            with lock:
                for p in data:
                    if not isinstance(p, dict):
                        continue
                    pic = self._featured(p)
                    tags = p.get("tags")
                    if not isinstance(tags, list):
                        continue
                    for t in tags:
                        try:
                            t = int(t)
                        except Exception:
                            continue
                        cnt[t] = cnt.get(t, 0) + 1
                        if pic and t not in cover:
                            cover[t] = pic

        ths = []
        for pg in range(1, self.subpage + 1):
            th = threading.Thread(target=work, args=(pg,), daemon=True)
            ths.append(th)
            th.start()
        for th in ths:
            try:
                th.join(timeout=12)
            except Exception:
                pass

        out = []
        if cnt:
            ids = [t for t, _c in sorted(cnt.items(), key=lambda x: -x[1])[:120]]
            info = {}
            for i in range(0, len(ids), 100):
                chunk = ids[i:i + 100]
                data, _ = self._json(API + "/tags",
                                     {"include": ",".join(str(x) for x in chunk),
                                      "per_page": 100,
                                      "_fields": "id,name,slug,count"}, ttl=CACHE_CAT)
                if isinstance(data, list):
                    for t in data:
                        if isinstance(t, dict):
                            info[_int(t.get("id"), 0, 0, 10 ** 9)] = t
            cname = self._cat_name(cid)
            for t in ids:
                d = info.get(t) or {}
                name = _clean(d.get("name"))
                slug = _clean(d.get("slug"))
                if not name:
                    continue
                # 跟大分类同名的标签没意义(点进去就是同一个分类),滤掉
                if name.lower() == cname.lower() or slug == _clean(catkey).lower():
                    continue
                out.append({
                    "id": t,
                    "name": name,
                    "count": cnt.get(t, 0),
                    "pic": cover.get(t, ""),
                    "total": _int(d.get("count"), 0, 0, 10 ** 9),
                })
                if len(out) >= SUB_MAX:
                    break
        with self._lock:
            self._sub_cache[ck] = (time.time(), out)
        return out

    def _sub_cards(self, catkey, pg):
        """大分类点进来看到的:小分类 VOD 卡片列表"""
        cid = self._cat_key(catkey)
        cname = self._cat_name(catkey)
        subs = self._subcats(catkey)
        cards = []
        if cid:
            # 第一张永远是「全部」,想直接刷整个分类的图点它
            total = 0
            for c in self._cats():
                if str(c[0]) == cid:
                    total = c[3]
                    break
            cards.append({
                "vod_id": "l:" + cid,
                "vod_name": "📁 全部 · %s" % cname,
                "vod_pic": subs[0]["pic"] if subs else "",
                "vod_remarks": ("共 %d 组" % total) if total else "全部作品",
                "vod_actor": "",
                "vod_content": "直接刷这个分类下的全部作品图片",
                "vod_tag": "folder",
            })
        for s in subs:
            cards.append({
                "vod_id": "t:%s:%d" % (cid, s["id"]),
                "vod_name": s["name"],
                "vod_pic": s["pic"],
                "vod_remarks": ("点开看图 · %d 组" % s["count"]) if s["count"] else (
                    ("点开看图 · 共 %d 组" % s["total"]) if s["total"] else "点开看图"),
                "vod_actor": "",
                "vod_content": "%s · %s" % (cname, s["name"]),
                "vod_tag": "folder",
            })
        if not cards:
            cards = [{
                "vod_id": "l:" + (cid or "0"),
                "vod_name": "📁 全部 · %s" % cname,
                "vod_pic": "",
                "vod_remarks": "点开看图",
                "vod_actor": "",
                "vod_content": "小分类没整理出来,先进去看全部作品",
                "vod_tag": "folder",
            }]
        return self._page(cards, 1, 1, len(cards))

    def _warm(self):
        """后台把前几个大分类的小分类先算好(顺序来、慢慢来),用户点进去就是秒开"""
        with self._lock:
            if self._warmed:
                return
            self._warmed = True

        def work():
            try:
                time.sleep(1.2)             # 先让首页自己跑完
                for cid, slug, _n, _c in self._cats()[:4]:
                    key = str(cid) if cid else slug
                    try:
                        self._subcats(key)
                    except Exception:
                        pass
                    time.sleep(0.5)
            except Exception:
                pass

        try:
            threading.Thread(target=work, daemon=True).start()
        except Exception:
            pass

    # ==================== 看图队列(无限往下接) ====================

    def _q_new(self, items, pos, title, more=None):
        """开一条看图流:items 是作品列表(vod_id 形式),pos 是从第几个开始看。
        more() 会在队列看完了被叫去拉下一批作品,于是能一直刷下去。"""
        with self._lock:
            self._qserial += 1
            key = "q%s_%d" % (self._tag, self._qserial)
            self._queues[key] = {
                "items": list(items or []),
                "i": max(0, int(pos or 0)),
                "seen": set(),
                "more": more,
                "title": title or "",
                "photos": [],
                "lock": threading.Lock(),
                "end": False,
                "page": 1,
            }
            if len(self._queues) > QMAX:
                old = sorted(self._queues, key=lambda k: _int(k[1:], 0, 0, 10 ** 9))
                for k in old[:len(self._queues) - QMAX]:
                    if k != key:
                        self._queues.pop(k, None)
        return key

    def _q_get(self, key):
        with self._lock:
            return self._queues.get(key)

    def _q_more(self, q):
        """队列见底 → 让 more() 去拉下一批作品"""
        fn = q.get("more")
        if not fn or q.get("end"):
            q["end"] = True
            return []
        try:
            nxt = fn() or []
        except Exception:
            nxt = []
        if not nxt:
            q["end"] = True
            return []
        q["items"].extend(nxt)
        return nxt

    def _vm_next(self):
        """取下一组图(至少一篇作品;图少就多补几篇)。返回 (给页面的列表, 是否到底)"""
        q = self._vm
        if not q:
            return [], True
        out = []
        with q["lock"]:
            guard = 0
            while len(out) < 24 and guard < 4:
                guard += 1
                if q["i"] >= len(q["items"]):
                    if not self._q_more(q):
                        break
                    if q["i"] >= len(q["items"]):
                        break
                vid = q["items"][q["i"]]
                q["i"] += 1
                if vid in q["seen"]:
                    continue
                q["seen"].add(vid)
                title, imgs, _link = self._post_imgs(vid)
                if not imgs:
                    continue
                short = (title or "")[:40]
                for u in imgs:
                    rec = {"u": u, "c": self._chain(u), "w": short}
                    out.append(rec)
                    q["photos"].append(rec)
        return out, bool(not out and q.get("end"))

    @staticmethod
    def _chain(u):
        """加载失败时的备选地址(去尺寸段的原图)"""
        try:
            p = urlparse(u)
            base = _SIZE_SEG.sub("", p.path)
            if base != p.path:
                return "https://" + p.netloc + base
        except Exception:
            pass
        return ""

    # ==================== 首页 / 分类 ====================

    def homeContent(self, filter=False):
        classes = [
            {"type_id": "latest", "type_name": "⭐ Latest(推荐)"},
            {"type_id": "hot", "type_name": "🔥 Top Hot(热门)"},
        ]
        for cid, slug, name, cnt in self._cats():
            key = str(cid) if cid else slug
            tip = (" (%d)" % cnt) if cnt else ""
            classes.append({"type_id": "c:" + key, "type_name": "📂 " + name + tip})

        sort_vals = [{"n": "🆕 最新发布", "v": "date"},
                     {"n": "♻️ 最近更新", "v": "modified"},
                     {"n": "🔤 标题 A-Z", "v": "title"}]
        filters = {
            "latest": [{"key": "sort", "name": "排序", "value": sort_vals}],
            "hot": [{"key": "range", "name": "选榜",
                     "value": [{"n": n, "v": k} for k, n, _p in HOT_BOARDS]}],
        }
        for cid, slug, _name, _c in self._cats():
            key = str(cid) if cid else slug
            filters["c:" + key] = [{"key": "sort", "name": "排序", "value": sort_vals}]
            filters["l:" + key] = [{"key": "sort", "name": "排序", "value": sort_vals}]
        self._warm()
        return {"class": classes, "filters": filters}

    def homeVideoContent(self):
        return self.categoryContent("latest", "1", False, None)

    @staticmethod
    def _ext_val(extend, key):
        v = None
        if isinstance(extend, dict):
            v = extend.get(key)
        elif isinstance(extend, str) and extend.strip():
            try:
                j = json.loads(extend)
                if isinstance(j, dict):
                    v = j.get(key)
            except Exception:
                for kv in re.split(r"[&,;]+", extend):
                    if "=" in kv:
                        k, val = kv.split("=", 1)
                        if _clean(k).lower() == key:
                            v = val
        return _clean(v)[:40] if v else ""

    def _queue_cards(self, posts, title, more):
        """一列作品 → 卡片 + 看图队列。
        ⛔ 卡片绝对不挂 action(血泪教训):客户端的点击分发是
            if (item.isAction()) … else if (item.isFolder())
           只要 action 非空,客户端就只调一次 action(),而 py 源这边的 action 分发
           在部分客户端(尤其盒子端)压根不回传 —— 表现就是「点了完全没反应」。
           Pinterest2 v1.5 已经踩过这个坑,这里走同一条稳的路:
           普通卡片 → 详情层 → 🖼 查看图片线路 / 详情起来自动弹看图窗。"""
        ids = [("p:" + str(p.get("id"))) for p in posts if isinstance(p, dict) and p.get("id")]
        qkey = self._q_new(ids, 0, title, more)
        items = []
        for i, p in enumerate(posts):
            if not isinstance(p, dict) or not p.get("id"):
                continue
            c = self._card(p, title)
            c["vod_id"] = "p:%s|%s|%d" % (str(p.get("id")), qkey, i)
            items.append(c)
        return items, qkey, ids

    def _wall(self, pg, title, cat=None, tag=None, orderby="date", search=None):
        """图片墙(整片封面) + 顺带把这一列作品挂进看图队列的 more 里,能一直往下翻"""
        orderby = orderby if orderby in ("date", "modified", "title", "relevance") else "date"
        state = {"pg": pg}

        def more():
            if state["pg"] >= PAGE_MAX:
                return []
            state["pg"] += 1
            if search:
                ps, _pg, _t = self._list_posts_paged(state["pg"], None, "relevance", search)
            else:
                ps, _pg, _t = self._list_posts_paged(state["pg"], cat, orderby, None, tag)
            return [("p:" + str(p.get("id"))) for p in ps
                    if isinstance(p, dict) and p.get("id")]

        posts, pages, total = self._list_posts_paged(pg, cat, orderby, search, tag)
        items, _qkey, _ids = self._queue_cards(posts, title, more)
        if pages > 1:
            self._prefetch(pg + 1, pages, title, cat, tag, orderby, search)
        return self._page(items, pg, max(pages, 1), total)

    def _prefetch(self, pg, pages, title, cat, tag, orderby, search):
        """后台先把下一页作品拉回来,翻页基本秒开(同一个 key 只预取一次)"""
        key = "pf:%s:%s:%s:%s:%s" % (pg, cat, tag, search, orderby)
        with self._lock:
            if key in self._prefetching:
                return
            self._prefetching.add(key)

        def work():
            try:
                time.sleep(0.15)
                if search:
                    self._list_posts(pg, None, "relevance", search)
                else:
                    self._list_posts(pg, cat, orderby, None, tag)
            except Exception:
                pass
            finally:
                with self._lock:
                    self._prefetching.discard(key)

        try:
            threading.Thread(target=work, daemon=True).start()
        except Exception:
            with self._lock:
                self._prefetching.discard(key)

    def categoryContent(self, tid, pg, filter=False, extend=None):
        tid = str(tid or "")
        pg = _int(pg, 1, 1, 100000)
        orderby = self._ext_val(extend, "sort") or self.sort
        if orderby not in ("date", "modified", "title"):
            orderby = self.sort

        # ⭐ Latest(推荐)
        if tid in ("", "latest"):
            return self._wall(pg, "最新发布", None, None, orderby)

        # 🔥 Top Hot(热门)
        if tid == "hot":
            key = self._ext_val(extend, "range") or self.hot_default
            if key not in HOT_PATH:
                key = self.hot_default
            items, pagecount = self._hot_cards(key, pg)
            ids = []
            for it in items:
                ids.append(str(it.get("vod_id") or ""))
            label = "热门榜"
            st = {"pg": pg}

            def more():
                if st["pg"] >= PAGE_MAX:
                    return []
                st["pg"] += 1
                nxt, _pc = self._hot_cards(key, st["pg"])
                return [str(x.get("vod_id") or "") for x in nxt]

            qkey = self._q_new(ids, 0, label, more)
            out = []
            for i, it in enumerate(items):
                it = dict(it)
                it["vod_id"] = "%s|%s|%d" % (str(it.get("vod_id") or ""), qkey, i)
                out.append(it)
            return self._page(out, pg, max(pagecount, 1), len(out))

        # 📂 大分类:默认先列小分类,点小分类才看图(sub=0 时直接出图墙)
        if tid.startswith("c:"):
            if self.subnav:
                return self._sub_cards(tid[2:], pg)
            cid = self._cat_key(tid[2:])
            if not cid:
                return self._page([], pg, 1, 0)
            return self._wall(pg, self._cat_name(cid), cid, None, orderby)

        # 📁 大分类「全部」→ 图片墙
        if tid.startswith("l:"):
            cid = self._cat_key(tid[2:])
            if not cid:
                return self._page([], pg, 1, 0)
            return self._wall(pg, self._cat_name(cid), cid, None, orderby)

        # 🖼 某个小分类 → 图片墙
        if tid.startswith("t:"):
            body = tid[2:]
            if ":" not in body:
                return self._page([], pg, 1, 0)
            ck, tk = body.split(":", 1)
            cid = self._cat_key(ck)
            tname = ""
            try:
                tid_i = int(tk)
            except Exception:
                tid_i = 0
            for s in self._subcats(ck):
                if int(s["id"]) == tid_i:
                    tname = s["name"]
                    break
            label = ("%s · %s" % (self._cat_name(cid), tname)) if tname else self._cat_name(cid)
            return self._wall(pg, label, cid or None, tk or None, orderby)

        return self._page([], pg, 1, 0)

    # ==================== 搜索 ====================

    def searchContent(self, key, quick=False, pg="1"):
        key = _clean(key)
        if not key:
            return self._page([], 1, 1, 0)
        pg = _int(pg, 1, 1, 100000)
        r = self._wall(pg, "搜索·%s" % key[:20], None, None, "relevance", key)
        if not r["list"] and pg == 1:
            # 接口搜不到(有些中文词分词不认)→ 用站内搜索页兜底
            items = self._search_html(key)
            if items:
                ids = [str(x.get("vod_id") or "") for x in items]

                def more():
                    return []

                qkey = self._q_new(ids, 0, "搜索·%s" % key[:20], more)
                out = []
                for i, x in enumerate(items):
                    x = dict(x)
                    x["vod_id"] = "%s|%s|%d" % (str(x.get("vod_id") or ""), qkey, i)
                    out.append(x)
                return self._page(out, 1, 1, len(out))
        return r

    def _search_html(self, key):
        txt, _ = self._fetch(SITE + "/", {"s": key}, ttl=HOT_TTL)
        if not txt:
            return []
        host = urlparse(SITE).netloc
        arts = re.findall(r"<article[^>]*class=\"[^\"]*jeg_post[^\"]*\"[^>]*>(.*?)</article>",
                          txt, re.S)
        items, seen = [], set()
        for a in arts:
            m = re.search(r'<a href="(https?://[^"]+)"', a)
            if not m:
                continue
            u = html_lib.unescape(m.group(1))
            if host not in u or u in seen:
                continue
            seen.add(u)
            im = re.search(r'<img[^>]+(?:data-src|src)="([^"]+)"', a, re.I)
            tt = re.search(r'class="jeg_post_title"[^>]*>\s*<a[^>]*>(.*?)</a>', a, re.S)
            items.append({
                "vod_id": "u:" + u,
                "vod_name": _clean(tt.group(1)) if tt else urlparse(u).path.strip("/").split("/")[-1],
                "vod_pic": urljoin(SITE + "/", im.group(1)) if im else "",
                "vod_remarks": "搜索",
                "vod_actor": "",
                "vod_content": "",
            })
        return items[:max(self.per, 20)]

    # ==================== 图集解析 ====================

    def _post_by_id(self, pid, ttl=CACHE_DETAIL):
        data, _ = self._json(API + "/posts/" + str(pid),
                             {"_fields": "id,link,title,date,content,featured_media,excerpt"},
                             ttl=ttl)
        return data if isinstance(data, dict) else None

    def _post_by_slug(self, slug, ttl=CACHE_DETAIL):
        data, _ = self._json(API + "/posts",
                             {"slug": slug,
                              "_fields": "id,link,title,date,content,featured_media,excerpt",
                              "per_page": 1}, ttl=ttl)
        if isinstance(data, list) and data:
            return data[0]
        return None

    def _post_from_html(self, url, ttl=CACHE_DETAIL):
        """接口全挂时的兜底:直接抓文章页,正文区里把图抠出来"""
        txt, _ = self._fetch(url, ttl=ttl)
        if not txt:
            return None
        body = txt
        m = re.search(r'<div class="[^"]*(?:jeg_inner_content|content-inner|entry-content)[^"]*"[^>]*>(.*?)'
                      r'<div class="[^"]*(?:jeg_share|jeg_post_tags|jeg_prevnext)[^"]*"', txt, re.S)
        if m:
            body = m.group(1)
        t = re.search(r"<title>(.*?)</title>", txt, re.S)
        return {"title": _clean(t.group(1)) if t else "", "content": body, "link": url}

    def _img_ok(self, u):
        if not u or not u.startswith("http"):
            return False
        if "/wp-content/uploads/" not in u and "/uploads/" not in u:
            return False
        if not _IMG_OK.search(urlparse(u).path):
            return False
        if _IMG_BAD.search(u):
            return False
        return True

    def _imgs(self, content_html):
        """正文 HTML → 有序去重的原图列表"""
        if not content_html:
            return []
        h = html_lib.unescape(content_html)
        full_of = {}
        for m in re.finditer(r'<a[^>]+href="([^"]+\.(?:jpe?g|png|webp|gif|avif))"', h, re.I):
            u = m.group(1)
            if self._img_ok(u):
                full_of[_stem_key(u)] = u
        out, seen = [], set()
        for m in re.finditer(r"<img[^>]+>", h, re.I):
            tag = m.group(0)
            u = ""
            for k in ("data-src", "data-lazy-src", "data-original", "src"):
                mm = re.search(k + r'=["\']([^"\']+)["\']', tag, re.I)
                if mm and mm.group(1).strip():
                    u = html_lib.unescape(mm.group(1).strip())
                    break
            if not u:
                continue
            if not u.startswith("http"):
                u = urljoin(SITE + "/", u)
            if not self._img_ok(u):
                continue
            full = full_of.get(_stem_key(u))
            if full and not _has_size(full):     # 有真原图就用原图
                u = full
            if u in seen:
                continue
            seen.add(u)
            out.append(u)
        return out

    def _post_imgs(self, vid, fresh=None):
        """拿一篇作品的图集。vid 可以是 p:123 也可以是 u:https://.../slug/
        fresh=True → 这次现拉(不吃任何缓存)。点开看图就走这条:
        点哪一套就现拉哪一套,不认位置、不认共享列表、不吃缓存。"""
        vid = str(vid or "")
        if "|" in vid:
            vid = vid.split("|")[0]
        if fresh is None:
            fresh = not getattr(self, "cache", 0)
        ttl = 0 if fresh else CACHE_DETAIL
        post = None
        if vid.startswith("u:"):
            url = vid[2:]
            slug = urlparse(url).path.strip("/").split("/")[-1]
            if slug:
                post = self._post_by_slug(slug, ttl)
            if not post:
                post = self._post_from_html(url, ttl)
        else:
            pid = vid.split(":")[-1]
            if pid.isdigit():
                post = self._post_by_id(pid, ttl)
        if not post:
            return "", [], ""
        t = post.get("title")
        title = _clean(t.get("rendered") if isinstance(t, dict) else t)
        raw = post.get("content")
        body = raw.get("rendered") if isinstance(raw, dict) else (raw or "")
        imgs = self._imgs(body)
        link = _clean(post.get("link")) or ""
        if not imgs and link:
            alt = self._post_from_html(link, ttl)
            if alt:
                imgs = self._imgs(alt.get("content") or "")
                if not title:
                    title = _clean(alt.get("title"))
        return title, imgs, link

    def detailContent(self, ids):
        """详情层 —— 现在这是主路(卡片不挂 action 了)。
        卡片点进来就落到这里:把图集给出来,同时**页面一起来就把看图窗弹出来**
        (约 0.45 秒),用户感觉就是「点一下直接看图」。
        客户端会同时开详情页/播放页 —— 关窗时垫在下面的页面一起收掉,返回一次回列表。"""
        vid = ""
        try:
            vid = str(ids[0] if isinstance(ids, (list, tuple)) else ids or "")
        except Exception:
            vid = ""
        if not vid:
            return {"list": []}
        base = vid.split("|")[0]
        parts = vid.split("|")
        qkey = parts[1] if len(parts) > 1 else ""
        try:
            pos = int(parts[2]) if len(parts) > 2 else 0
        except Exception:
            pos = 0
        title, imgs, link = self._post_imgs(base)
        if not imgs:
            return {"list": []}
        cover = imgs[0]
        if not self._q_get(qkey):
            # 队列没了(客户端重启 / 从别的入口点进来)→ 现开一条只含这一篇的,
            # 保证点了一定能弹看图窗
            qkey = self._q_new([base], 0, title or "", None)
            pos = 0
        content = title or "XiuRen"
        content += "\n图片:%d 张" % len(imgs)
        if link:
            content += "\n" + link
        item = {
            "vod_id": vid,
            "vod_name": title or "XiuRen",
            "vod_pic": cover,
            "vod_remarks": "共 %d 张" % len(imgs),
            "vod_actor": "",
            "vod_content": content.strip(),
            "pictures": imgs,
        }
        if self.line:
            if self.webview:
                # 旧版:走私有 WebView 桥(需要客户端支持 ZAKA_APPEND 等能力)
                item["vod_play_from"] = "🖼 查看图片"
                # 把作品 id 直接写进线路:点哪套就是哪套(队列只用来"往下接")
                item["vod_play_url"] = "查看图片$img|%s|%s|%d" % (base, qkey, max(0, pos))
                # 页面起来之后自己弹看图页(不用再点一次「查看图片」)
                self._auto_open(vid, title)
            else:
                # 默认:按 base.spider 图文源契约输出 pics:// 播放串。
                # 多张图以 && 分隔,主流 TVBox / 影视仓 都会以画廊/幻灯片形式展示,
                # 不依赖任何私有 WebView 桥,兼容性最好。
                play_url = "看图$pics://" + "&&".join(imgs)
                item["vod_play_from"] = "🖼 看图"
                item["vod_play_url"] = play_url
        return {"list": [item], "parse": 0, "jx": 0}

    # ==================== action:点卡片直接进看图页 ====================

    def action(self, action, value):
        a = str(action or "").strip().lower()
        v = str(value or "").strip()
        if a in ("img", "pic", "photo", "view", "看图"):
            try:
                self._open_from_card(v)
            except Exception as e:
                self._toast("看图页没弹出来:" + str(e)[:60])
            return ""
        # 兜底:万一客户端把 folder 卡片的 vod_id 当 action 派发过来
        if v.startswith("c:") or v.startswith("l:") or v.startswith("t:"):
            return ""
        return ""

    def _open_from_card(self, vid):
        """从卡片直接开看图页。动作全丢后台,别卡住客户端线程。"""
        def work():
            base = vid.split("|")[0]
            parts = vid.split("|")
            qkey = parts[1] if len(parts) > 1 else ""
            try:
                pos = int(parts[2])
            except Exception:
                pos = 0
            q = self._q_get(qkey)
            title = (q.get("title") if q else "") or "看图"
            # 只把作品 id 交给看图页 —— 队列在不在都不影响取图
            self._popup_gallery(title, base, qkey, pos)

        try:
            threading.Thread(target=work, daemon=True).start()
        except Exception:
            work()

    def _auto_open(self, vid, title):
        """详情页兜底弹窗

        默认(auto=2):等 2.5 秒 —— 这 2.5 秒里客户端基本已经靠「自动播图片线路」
        把看图窗弹出来了(和 Pinterest 一模一样的路),那就什么都不做(不抢、不叠、不闪);
        只有极少数不自动播线路的客户端才补弹一次,保证一定看得到图。
        auto=1 回到上一版「详情页一起来 0.45 秒就弹」,auto=0 完全不补。
        """
        if not self.auto:
            return

        def work():
            time.sleep(0.45 if self.auto == 1 else 2.5)
            base = vid.split("|")[0]
            parts = vid.split("|")
            qkey = parts[1] if len(parts) > 1 else ""
            try:
                pos = int(parts[2]) if len(parts) > 2 else 0
            except Exception:
                pos = 0
            # 客户端已经靠「自动播图片线路」把窗弹出来过了 → 不重复弹(不闪)
            try:
                with self._pop_lock:
                    if self._pop_alive and self._pop_key == base:
                        return
            except Exception:
                pass
            ok = False
            try:
                ok = self._popup_gallery(title or "", base, qkey, pos,
                                         chain_close=True, quick=False)
            except Exception:
                ok = False
            if not ok:
                # 窗没真弹出来(页面还没就绪 / 被盖住)→ 隔一秒再怼一次,不静默失败
                try:
                    time.sleep(1.0)
                    self._popup_gallery(title or "", base, qkey, pos,
                                        chain_close=True, quick=False)
                except Exception:
                    pass

        try:
            threading.Thread(target=work, daemon=True).start()
        except Exception:
            pass

    # ==================== 看图页(原生弹窗 + WebView) ====================

    def _popup_gallery(self, title, postkey, qkey="", pos=0, chain_close=False, quick=True):
        """开看图窗(第一屏只认作品 id)。

        v3.0 病根:第一屏以前是去**共享队列**里拿"当前攒下来的那批图"——
        队列是整列作品共用的,攒出来的又永远从第 0 张开始 →
        在同一个列表里点不同的几套,弹出来全是同一套;队列一重建又集体换一套
        (于是"过一阵子再打开变成别的内容")。
        现在:弹窗前拿**这一套的作品 id** 现拉这一套的图;
        队列/位置只用来决定「往下接哪一套」,再也不参与取图。
        窗还开着又点了另一套 → 原地换内容(ZAKA_RESET),不叠第二层窗。"""
        postkey = str(postkey or "")
        qkey = str(qkey or "")
        if not postkey and qkey:
            # 兼容手里还捏着旧卡片的:只有「队列 + 位置」,按位置去队列里查出作品 id
            q0 = self._q_get(qkey)
            items = list((q0.get("items") if q0 else None) or [])
            if items:
                try:
                    k0 = max(0, min(int(pos or 0), len(items) - 1))
                except Exception:
                    k0 = 0
                postkey = str(items[k0])
        if not postkey:
            return False
        # 1) 现拉这一套(认作品 id —— 不认位置、不认共享列表、不吃缓存)
        name, imgs = "", []
        try:
            name, imgs, _link = self._post_imgs(postkey, fresh=True)
        except Exception:
            name, imgs = "", []
        name = _clean(name) or _clean(title) or "看图"
        if not imgs:
            return False
        # 2) 位置只用来决定「往下接哪一套」:从这一套的下一条开始
        self._vm = None
        q = self._q_get(qkey) if qkey else None
        if q:
            try:
                k = list(q.get("items") or []).index(postkey)
            except Exception:
                k = -1
            if k >= 0:
                q["i"] = k + 1
                q["photos"] = []
                self._vm = q
        recs = [{"u": u, "c": self._chain(u), "w": name[:40]} for u in imgs]
        btitle = "%s · 本套 %d 张" % (name, len(recs))
        key = postkey
        now = time.time()
        with self._pop_lock:
            if self._pop_alive and self._pop_key == key:
                return True                     # 窗开着,看的就是这一套
            swap = self._pop_js if (self._pop_alive and self._pop_js) else None
            if swap is None:
                if now - self._pop_busy < 4:
                    return False
                self._pop_busy = now
        if swap is not None:
            # 窗开着但看的是另一套 → 原地把内容换掉(不叠窗、不闪、不重开)
            try:
                swap("window.ZAKA_RESET&&window.ZAKA_RESET(%s,%s)"
                     % (json.dumps(recs, ensure_ascii=False),
                        json.dumps(btitle, ensure_ascii=False)))
                with self._pop_lock:
                    self._pop_key = key
                return True
            except Exception:
                pass
        html = self._gallery_html(btitle, recs)
        try:
            return self._popup(html, key, chain_close=chain_close, title=btitle,
                               quick=quick, pre=True)
        finally:
            with self._pop_lock:
                self._pop_busy = 0.0

    def _esc(self, s):
        """HTML 转义(看图页标题要用)"""
        s = "" if s is None else str(s)
        try:
            return html_lib.escape(s)
        except Exception:
            return (s.replace("&", "&amp;").replace("<", "&lt;")
                     .replace(">", "&gt;").replace('"', "&quot;"))

    def _slide_rec(self, rec):
        """一张图 → 看图页要的 {u: 主链, c: 备用链(| 分隔), w: 落款}"""
        return {"u": str(rec.get("u") or ""),
                "c": str(rec.get("c") or ""),
                "w": str(rec.get("w") or "")}

    # ==================== 内置黑屏占位视频(治「正在切换站源」) ====================

    def _ph_dir(self):
        """放小文件的目录:优先应用缓存目录(可写就缓存住),拿不到再退临时目录

        临时目录**不缓存** —— 安卓上它常常是不可写的 /tmp,万一先走到这条路,
        缓存住就再也升不回应用缓存目录了(占位片写不出来 → 又回 about:blank → 又切源)。"""
        if _PH_DIR_CACHE[0]:
            return _PH_DIR_CACHE[0]
        try:
            act = self._activity()
            if act is not None:
                d = act.getCacheDir().getAbsolutePath()
                if d:
                    _PH_DIR_CACHE[0] = str(d)
                    return str(d)
        except Exception:
            pass
        try:
            import tempfile
            d = tempfile.gettempdir()
            try:                              # 探一下真能写才用
                probe = os.path.join(d, ".zaka_w")
                with open(probe, "wb") as f:
                    f.write(b"1")
                os.remove(probe)
                return d
            except Exception:
                return ""
        except Exception:
            return ""

    def _ph_http(self, path):
        """本机回环小服务:把占位片用 http://127.0.0.1:端口/xxx.mp4 发出去(起不来返回空串)

        为什么不用 file://:个别播放器的数据源只认 http(s),file:// 播不动 → 又去切站源。
        回环 http 谁都认;片子 8KB,一次读完,后面 4 小时不再要数据,几乎不吃流量。"""
        with _PH_LOCK:
            if _PH_SRV["url"]:
                return _PH_SRV["url"]
        try:
            import http.server
            try:
                with open(path, "rb") as f:
                    body = f.read()
            except Exception:
                return ""
            total = len(body)

            class Handler(http.server.BaseHTTPRequestHandler):
                protocol_version = "HTTP/1.1"

                def log_message(self, *a):
                    pass

                def _head(self, code, start, end):
                    self.send_response(code)
                    self.send_header("Content-Type", "video/mp4")
                    self.send_header("Accept-Ranges", "bytes")
                    self.send_header("Content-Length", str(max(0, end - start + 1)))
                    if code == 206:
                        self.send_header("Content-Range",
                                         "bytes %d-%d/%d" % (start, end, total))
                    self.end_headers()

                def _rng(self):
                    r = str(self.headers.get("Range") or "").strip().lower()
                    if not r.startswith("bytes=") or total <= 0:
                        return None
                    piece = r[6:].split(",")[0].strip()
                    a, _sep, b = piece.partition("-")
                    try:
                        if a == "":
                            s2 = max(0, total - int(b))
                            e2 = total - 1
                        else:
                            s2 = int(a)
                            e2 = int(b) if b else total - 1
                    except Exception:
                        return None
                    s2 = max(0, min(s2, total - 1))
                    e2 = max(s2, min(e2, total - 1))
                    return s2, e2

                def do_GET(self):
                    try:
                        r = self._rng()
                        if r:
                            self._head(206, r[0], r[1])
                            self.wfile.write(body[r[0]:r[1] + 1])
                            return
                        self._head(200, 0, total - 1)
                        self.wfile.write(body)
                    except Exception:
                        pass

                def do_HEAD(self):
                    try:
                        self._head(200, 0, total - 1)
                    except Exception:
                        pass

            srv = None
            for nm in ("ThreadingHTTPServer", "HTTPServer"):
                cls = getattr(http.server, nm, None)
                if cls is None:
                    continue
                try:
                    srv = cls(("127.0.0.1", 0), Handler)
                    break
                except Exception:
                    srv = None
            if srv is None:
                return ""
            port = int(srv.server_address[1])
            th = threading.Thread(target=srv.serve_forever)
            th.daemon = True
            th.start()
            url = "http://127.0.0.1:%d/%s" % (port, PH_NAME)
            with _PH_LOCK:
                _PH_SRV["srv"] = srv
                _PH_SRV["url"] = url
            return url
        except Exception:
            return ""

    def _ph_video(self):
        """图片线路回一条**真能播**的视频地址(黑屏 / 无声 / 4 小时 / 8KB)

        病根:详情页第一条线路就是「🖼 查看图片」,客户端进场自动播它。
        以前回 about:blank 或图片直链 → 播放器一播就失败 → 客户端判定"坏源" →
        自己去找别的站源(「正在切换站源」一直闪)。给它一条播得动的,播放器不报错,
        自然就不会切源。优先本机 http(播放器最认),退一步 file://。"""
        if not self.ph:
            return ""
        try:
            with self._ph_lock:
                d = self._ph_dir()
                if not d:
                    return ""
                p = os.path.join(d, PH_NAME)
                ok = False
                try:
                    ok = os.path.exists(p) and os.path.getsize(p) == PH_SIZE
                except Exception:
                    ok = False
                if not ok:
                    with open(p, "wb") as f:
                        f.write(base64.b64decode(PH_MP4_B64))
            url = self._ph_http(p)
            if url:
                return url
            return "file://" + p
        except Exception:
            return ""

    # ==================== 看图模式记忆 ====================

    def _mode_file(self):
        d = self._ph_dir()
        return os.path.join(d, "zaka_view.txt") if d else ""

    def _load_mode(self):
        """上次在看图页里选的那个模式,重启也记得"""
        try:
            p = self._mode_file()
            if p and os.path.exists(p):
                with open(p) as f:
                    self.view_mode = _int(f.read().strip(), self.view_mode, 0, 2)
        except Exception:
            pass

    def _save_mode(self):
        try:
            p = self._mode_file()
            if p:
                with open(p, "w") as f:
                    f.write(str(int(self.view_mode or 0)))
        except Exception:
            pass

    def _gallery_html(self, title, slides=None):
        """首屏图片直接塞进页面(JSON)—— 弹窗一出来就有图,不指望客户端回调。
        v2.2:三种看图模式(左右 / 上下无缝 / 瀑布流)都在页面里,右上角点一下切。"""
        slides = list(slides or [])
        data = [self._slide_rec(r) for r in slides]
        try:
            blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
        except Exception:
            blob = "[]"
        vm = int(self.view_mode or 0) % 3
        html = GALLERY_HTML.replace("###TITLE###", self._esc(title))
        html = html.replace("###MEDIA###", blob)
        html = html.replace("###MODE###", str(vm))
        html = html.replace("###MODENAME###", VIEW_NAMES[vm])
        html = html.replace("###TIP###", VIEW_TIPS[vm])
        html = html.replace("###IDX###", "0")
        html = html.replace("###COUNT###", str(len(data)))
        html = html.replace("###COUNTER###",
                            ("1 / %d" % len(data)) if data else "")
        return html

    def _popup(self, html, qkey, chain_close=False, title="", quick=False, pre=False):
        """挑一页把看图弹窗挂上去,返回真挂上了没。
        从列表卡片点进来时(quick)当前页就是列表,直接挂它,别等;
        从详情层进来时等页面起来,免得被后起来的页面盖住。
        v2.1:详情层默认不再给播放线路,所以**不该再有播放页** —— 等两轮没等到
        就别耗了,直接挂当前活着的页面,弹窗出得更快。"""
        act = None
        plyk = ("player", "playback", "exo", "ijkplayer")
        midk = ("vod", "detail", "album", "episode")
        rounds = 2 if quick else 8
        for i in range(rounds):
            acts = self._all_activities()
            if acts:
                live = [x for x in acts if not x[2]]
                ply = [x for x in live if any(k in x[0] for k in plyk)]
                if ply:
                    # 还留着播放页(用户自己填了 line=1)→ 优先挂它,别被盖住
                    act = ply[0][1]
                    break
                if quick:
                    act = (live or acts)[0][1]
                    break
                mid = [x for x in live if any(k in x[0] for k in midk)]
                if mid and i >= 2:
                    act = mid[0][1]
                    break
                if live and i >= 4:
                    # 没等到"像详情页"的,也别让用户干等 —— 挂当前这一页
                    act = live[0][1]
                    break
            time.sleep(0.15)
        if act is None:
            acts = self._all_activities()
            if acts:
                for c, a, _p in acts:
                    if any(k in c for k in plyk):
                        act = a
                        break
                else:
                    act = ([x for x in acts if not x[2]] or acts)[0][1]
        if act is None:
            return False
        return self._popup_ui(act, html, qkey, chain_close, title, pre)

    def _popup_ui(self, act, html, qkey, chain_close=False, title="", pre=False):
        try:
            from java import jclass, dynamic_proxy
            from java.lang import Runnable

            spider = self
            self._popup_host = act          # 记住这一页:关弹窗时先收它(不依赖客户端类名)
            # pre=True:首屏图已经写进页面了,别再白拉一次接口
            state = {"qkey": qkey, "loaded": [bool(pre)], "shown": False}

            class Run(dynamic_proxy(Runnable)):
                def __init__(self, fn):
                    super().__init__()
                    self.fn = fn

                def run(self):
                    self.fn()

            def ui():
                Dialog = jclass("android.app.Dialog")
                WebView = jclass("android.webkit.WebView")
                FrameLayout = jclass("android.widget.FrameLayout")
                Button = jclass("android.widget.Button")
                ColorDrawable = jclass("android.graphics.drawable.ColorDrawable")
                Color = jclass("android.graphics.Color")
                LP = jclass("android.widget.FrameLayout$LayoutParams")
                Gravity = jclass("android.view.Gravity")
                LinearLayout = jclass("android.widget.LinearLayout")
                LLP = jclass("android.widget.LinearLayout$LayoutParams")

                d = Dialog(act)
                d.requestWindowFeature(1)
                w = WebView(act)
                ws = w.getSettings()
                ws.setJavaScriptEnabled(True)
                ws.setDomStorageEnabled(True)
                ws.setUserAgentString(UA)
                w.setBackgroundColor(Color.BLACK)
                try:
                    ws.setLoadWithOverviewMode(True)
                    ws.setMediaPlaybackRequiresUserGesture(False)
                except Exception:
                    pass

                def js(code):
                    def go():
                        try:
                            w.evaluateJavascript(code, None)
                        except Exception:
                            pass
                    dispatch(go)

                def js_async(code):
                    def go():
                        try:
                            w.evaluateJavascript(code, None)
                        except Exception:
                            pass
                    try:
                        act.runOnUiThread(Run(go))
                    except Exception:
                        try:
                            act.getWindow().getDecorView().post(Run(go))
                        except Exception:
                            pass

                def dispatch(fn):
                    try:
                        act.runOnUiThread(Run(fn))
                    except Exception:
                        try:
                            act.getWindow().getDecorView().post(Run(fn))
                        except Exception:
                            pass

                def push(data, msg=""):
                    """把一批图推给页面(空的话就说一句)"""
                    if data:
                        js_async("window.ZAKA_APPEND&&window.ZAKA_APPEND(%s)"
                                 % json.dumps(data, ensure_ascii=False))
                    elif msg:
                        js_async("window.ZAKA_END&&window.ZAKA_END(%s)"
                                 % json.dumps(str(msg), ensure_ascii=False))

                gate = {"lock": threading.Lock(), "last": 0.0}

                def load_more(note=True):
                    """加载下一组作品,推给页面"""
                    with gate["lock"]:
                        now = time.time()
                        if now - gate["last"] < 0.8:
                            return
                        gate["last"] = now
                    def work():
                        try:
                            data, end = spider._vm_next()
                        except Exception:
                            data, end = [], False
                        if data:
                            push(data)
                        elif end:
                            push(None, "已经到底了")
                        else:
                            push(None, "")
                            js_async("window.ZAKA_INFO&&window.ZAKA_INFO('这一组没拉到图,滑一下再试')")
                    try:
                        threading.Thread(target=work, daemon=True).start()
                    except Exception:
                        work()

                def first_load():
                    with gate["lock"]:
                        if state["loaded"][0]:
                            return
                        state["loaded"][0] = True
                    load_more()

                # 页面加载完 → 拉第一组;同时用定时器兜底(有的客户端 onPageFinished 不响)
                try:
                    WC = jclass("android.webkit.WebViewClient")

                    class Cli(dynamic_proxy(WC)):
                        def __init__(self):
                            super().__init__()

                        def onPageFinished(self, view, url):
                            try:
                                first_load()
                            except Exception:
                                pass

                    w.setWebViewClient(Cli())
                except Exception:
                    pass

                try:
                    threading.Timer(0.45, first_load).start()
                except Exception:
                    pass

                # 页面滑到底 → console.log('ZAKA_MORE') → 这里接住去加载下一组
                try:
                    CC = jclass("android.webkit.WebChromeClient")

                    class Chrome(dynamic_proxy(CC)):
                        def __init__(self):
                            super().__init__()

                        def onReceivedTitle(self, view, t):
                            try:
                                s = str(t or "")
                                if s.startswith("IDX"):
                                    spider._cur_idx = int((s[3:].strip() or "0"))
                            except Exception:
                                pass

                        def onConsoleMessage(self, cm):
                            try:
                                msg = str(cm.message() or "")
                            except Exception:
                                return True
                            if "ZAKA_MORE" in msg:
                                try:
                                    load_more()
                                except Exception:
                                    pass
                            if "ZAKA_CUR:" in msg:
                                try:
                                    spider._cur_url = msg.split("ZAKA_CUR:", 1)[1].strip()
                                except Exception:
                                    pass
                            if "ZAKA_SETMODE:" in msg:
                                try:
                                    spider.view_mode = int(
                                        msg.split("ZAKA_SETMODE:", 1)[1].strip()[0])
                                    spider._save_mode()
                                except Exception:
                                    pass
                            return True

                    w.setWebChromeClient(Chrome())
                except Exception:
                    pass

                frame = FrameLayout(act)
                try:
                    frame.addView(w, LP(-1, -1))
                except Exception:
                    pass
                try:
                    w.loadDataWithBaseURL(SITE + "/", html, "text/html", "utf-8", None)
                except Exception:
                    pass

                def cur_photo():
                    # 页面上正显示哪张,页面自己会回报 —— 不再靠"第几个位置"去猜
                    u0 = str(getattr(spider, "_cur_url", "") or "")
                    if u0:
                        return {"u": u0}
                    q = spider._q_get(state["qkey"]) or {}
                    ph = q.get("photos") or []
                    try:
                        i = int(getattr(spider, "_cur_idx", 0))
                    except Exception:
                        i = 0
                    if not (0 <= i < len(ph)):
                        i = 0
                    return ph[i] if ph else {}

                def do_dl():
                    cur = cur_photo()
                    u = str(cur.get("u") or "")
                    if not u:
                        spider._toast("还没加载出图片")
                        return

                    def work():
                        try:
                            ok, m = spider._download(u)
                            spider._toast(("✅ " if ok else "❌ ") + m)
                        except Exception as e:
                            spider._toast("下载没起来:" + str(e)[:40])

                    try:
                        threading.Thread(target=work, daemon=True).start()
                    except Exception:
                        work()

                class Click(dynamic_proxy(jclass("android.view.View$OnClickListener"))):
                    def __init__(self, fn):
                        super().__init__()
                        self.fn = fn

                    def onClick(self, v):
                        try:
                            self.fn()
                        except Exception:
                            pass


                d.setContentView(frame)
                # 关窗回调必须**总是**挂:① 记下「窗已经关了」(防叠窗判据靠它)
                # ② 需要时把垫在下面的详情页一起收掉 —— 返回一次就回列表
                try:
                    DOL = jclass("android.content.DialogInterface$OnDismissListener")

                    class Dismiss(dynamic_proxy(DOL)):
                        def __init__(self):
                            super().__init__()

                        def onDismiss(self, dlg):
                            try:
                                spider._pop_alive = False
                                spider._pop_js = None
                                spider._pop_key = ""
                            except Exception:
                                pass
                            if chain_close:
                                try:
                                    spider._close_middle()
                                except Exception:
                                    pass

                    d.setOnDismissListener(Dismiss())
                except Exception:
                    pass
                d.show()
                try:
                    state["shown"] = True    # v2.1:窗真出来了,拿它判断要不要重试
                except Exception:
                    pass
                # 窗真出来了才算「开着」—— 没弹出来不算,别把下一次点击吞掉
                try:
                    spider._pop_alive = True
                    spider._pop_key = qkey
                    spider._popup_host = act
                    spider._pop_js = js_async        # 换另一套时原地换内容,不叠窗
                except Exception:
                    pass

                # 按钮栏是「装饰」——放到弹窗出来之后再搭,它出问题也不影响看图
                try:
                    dens = 1.0
                    try:
                        dens = float(act.getResources().getDisplayMetrics().density)
                    except Exception:
                        pass
                    bar = LinearLayout(act)
                    bar.setOrientation(1)

                    def mk_btn(text, fn, first=False):
                        b = Button(act)
                        b.setText(text)
                        try:
                            b.setTextSize(12)
                            b.setTextColor(Color.WHITE)
                            b.setBackgroundColor(Color.argb(215, 26, 26, 26))
                        except Exception:
                            pass
                        try:
                            b.setOnClickListener(Click(fn))
                        except Exception:
                            pass
                        bp = LLP(-2, -2)
                        try:
                            if not first:
                                bp.setMargins(0, int(8 * dens), 0, 0)
                        except Exception:
                            pass
                        bar.addView(b, bp)
                        return b

                    # v2.5:按钮直接写着当前是哪种模式,点一下换下一种(盒子遥控器也能按)
                    mnames = ["\u2194 \u5de6\u53f3", "\u2195 \u4e0a\u4e0b", "\u25a6 \u6c34\u5e03"]
                    mstate = [int(spider.view_mode or 0) % 3]

                    def next_mode():
                        mstate[0] = (mstate[0] + 1) % 3
                        try:
                            mbtn.setText("\U0001F500 \u770b\u56fe: " + mnames[mstate[0]])
                        except Exception:
                            pass
                        js_async("window.ZAKA_MODE&&window.ZAKA_MODE()")

                    mbtn = mk_btn("\U0001F500 \u770b\u56fe: " + mnames[mstate[0]], next_mode, True)
                    mk_btn("⬇️ 下载", do_dl)
                    mk_btn("⬇️➡️ 继续加载", lambda: load_more())

                    lp = LP(-2, -2, Gravity.BOTTOM | Gravity.RIGHT)
                    try:
                        lp.setMargins(0, 0, int(16 * dens), int(74 * dens))
                    except Exception:
                        pass
                    frame.addView(bar, lp)
                except Exception:
                    pass
                try:
                    win = d.getWindow()
                    if win:
                        win.getDecorView().setPadding(0, 0, 0, 0)
                        win.setBackgroundDrawable(ColorDrawable(Color.TRANSPARENT))
                        win.setLayout(-1, -1)
                except Exception:
                    pass

            act.getWindow().getDecorView().post(Run(ui))
            # 等 UI 线程把窗搭出来(最多 1.2 秒):真出来了才算成功,失败好重试
            for _ in range(12):
                if state.get("shown"):
                    return True
                time.sleep(0.1)
            return bool(state.get("shown"))
        except Exception as e:
            self._toast("看图页打不开:" + str(e)[:40])
            return False

    def _close_middle(self, max_depth=3):
        """把垫在弹窗下面的详情页 / 播放页收掉(主列表绝不动)"""
        KEYS = ("detail", "player", "playback", "vod", "episode", "album")

        def is_home(act):
            try:
                pm = act.getPackageManager()
                it = pm.getLaunchIntentForPackage(str(act.getPackageName()))
                home = str(it.getComponent().getClassName())
                return str(act.getClass().getName()) == home
            except Exception:
                return False

        def step(n, first=False):
            if n <= 0:
                return
            act = self._activity()
            if act is None:
                try:
                    threading.Timer(0.35, step, args=(n - 1, first)).start()
                except Exception:
                    pass
                return
            if first:
                host = getattr(self, "_popup_host", None)
                if host is not None:
                    self._popup_host = None
                    try:
                        if not is_home(host):
                            host.finish()
                            try:
                                threading.Timer(0.35, step, args=(n - 1, False)).start()
                            except Exception:
                                pass
                            return
                    except Exception:
                        pass
            try:
                cls = str(act.getClass().getName()).lower()
            except Exception:
                return
            if is_home(act) or not any(k in cls for k in KEYS):
                return
            try:
                act.finish()
            except Exception:
                return
            try:
                threading.Timer(0.35, step, args=(n - 1, False)).start()
            except Exception:
                pass

        try:
            threading.Timer(0.12, step, args=(max_depth, True)).start()
        except Exception:
            pass

    def _all_activities(self):
        """当前活着的 Activity 列表:[(类名(小写), activity, 是否 paused)]"""
        out = []
        try:
            from java import jclass
            JClass = jclass("java.lang.Class")
            AT = JClass.forName("android.app.ActivityThread")
            cur = AT.getMethod("currentActivityThread").invoke(None)
            f = AT.getDeclaredField("mActivities")
            f.setAccessible(True)
            for r in f.get(cur).values().toArray():
                rc = r.getClass()
                pf = rc.getDeclaredField("paused")
                pf.setAccessible(True)
                af = rc.getDeclaredField("activity")
                af.setAccessible(True)
                a = af.get(r)
                if a is None:
                    continue
                try:
                    if a.isFinishing():
                        continue
                except Exception:
                    pass
                try:
                    cls = str(a.getClass().getName()).lower()
                except Exception:
                    cls = ""
                out.append((cls, a, bool(pf.getBoolean(r))))
        except Exception:
            pass
        return out

    def _activity(self, prefer=None):
        acts = self._all_activities()
        if not acts:
            return None
        live = [x for x in acts if not x[2]]
        pool = live or acts
        if prefer:
            for c, a, _p in pool:
                if any(k in c for k in prefer):
                    return a
        return pool[0][1]

    def _toast(self, msg):
        try:
            from java import jclass, dynamic_proxy
            from java.lang import Runnable

            act = self._activity()
            if not act:
                return
            Toast = jclass("android.widget.Toast")

            class Run(dynamic_proxy(Runnable)):
                def __init__(self, fn):
                    super().__init__()
                    self.fn = fn

                def run(self):
                    self.fn()

            act.getWindow().getDecorView().post(Run(lambda: Toast.makeText(act, str(msg), 1).show()))
        except Exception:
            pass

    def _download(self, url, name=""):
        """存图:走系统下载器,图片落 Pictures/XiuRen"""
        try:
            from java import jclass
            Context = jclass("android.content.Context")
            Request = jclass("android.app.DownloadManager$Request")
            Uri = jclass("android.net.Uri")
            Environment = jclass("android.os.Environment")
            act = self._activity()
            if act is None:
                return False, "没找到可用的页面"
            dm = act.getSystemService(Context.DOWNLOAD_SERVICE)
            fn = name or (urlparse(url).path.rsplit("/", 1)[-1] or ("xiuren_%d.jpg" % int(time.time())))
            req = Request(Uri.parse(url))
            req.setTitle(fn)
            req.setNotificationVisibility(1)
            try:
                req.setDestinationInExternalPublicDir(Environment.DIRECTORY_PICTURES, "XiuRen/" + fn)
            except Exception:
                pass
            try:
                req.addRequestHeader("User-Agent", UA)
                req.addRequestHeader("Referer", SITE + "/")
            except Exception:
                pass
            try:
                act.runOnUiThread(_JRun(lambda: dm.enqueue(req)))
            except Exception:
                dm.enqueue(req)
            return True, "已开始下载:" + fn
        except Exception as e:
            return False, "下载没起来:" + str(e)[:40]

    # ==================== 播放(图片直链) ====================

    def playerContent(self, flag, id, vipFlags=None):
        url = str(id or "")
        # 有些客户端把详情页整行(「查看图片$img|xxx|0」)原样塞进来 → 只取 $ 后面那段
        if "$" in url and ("img|" in url or url.startswith("查看图片")):
            url = url.split("$")[-1]
        header = {"User-Agent": UA, "Referer": SITE + "/"}
        blank = {"parse": 0, "playUrl": "", "url": "about:blank", "header": header}
        # ---- 图文源 pics:// 播放串:直接透传,由播放器以画廊展示 ----
        # 兼容某些把整串(来源名$pics://...)当 id 传进来的客户端
        if "pics://" in url:
            p = url.find("pics://")
            return {"parse": 0, "playUrl": "", "url": url[p:], "header": header}
        # ---- 🖼 看图线路:点「查看图片」当场弹原生看图窗(和 Pinterest2 同一条路)----
        if url.startswith("img|"):
            parts = url.split("|")
            a1 = parts[1] if len(parts) > 1 else ""
            post, qkey, pos = "", "", 0
            if a1.startswith("p:") or a1.startswith("u:"):
                # 新格式:img|<作品id>|<队列key>|<位置> —— 直接认作品 id
                post = a1
                qkey = parts[2] if len(parts) > 2 else ""
                try:
                    pos = int(parts[3]) if len(parts) > 3 else 0
                except Exception:
                    pos = 0
            else:
                # 老格式:img|<队列key>|<位置>[|<作品id>] —— 手里还是旧卡片的也能看
                qkey = a1
                try:
                    pos = int(parts[2]) if len(parts) > 2 else 0
                except Exception:
                    pos = 0
                if len(parts) > 3:
                    post = parts[3]
            if not post and not self._q_get(qkey):
                return blank                    # 两手空空就别弹了,详情层还会补一次
            self._popup_gallery("", post, qkey, pos, chain_close=True, quick=False)
            # v2.5:默认回**本机黑屏占位片**(真能播 -> 播放器不报错 -> 不切源);
            # ph=0 才回 Pinterest 那种 about:blank(拿不到本机 http 时自动降级到它)
            ph = self._ph_video()
            if ph:
                return {"parse": 0, "playUrl": "", "url": ph, "header": header}
            return blank
        if url.startswith("u:") or url.startswith("p:"):
            _t, pics, _l = self._post_imgs(url)
            url = pics[0] if pics else ""
        return {
            "parse": 0,
            "playUrl": "",
            "url": url,
            "header": header,
        }

    def isVideoFormat(self, url):
        u = str(url or "").lower()
        return any(x in u for x in (".mp4", ".m3u8", ".mkv", ".flv", ".avi", ".ts"))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        with self._lock:
            self._cache.clear()
            self._queues.clear()
        try:
            if self._sess is not None:
                self._sess.close()
        except Exception:
            pass


def _JRun(fn):
    """给 _download 用的小包装(拿不到 java 环境时直接调用)"""
    try:
        from java import dynamic_proxy
        from java.lang import Runnable

        class R(dynamic_proxy(Runnable)):
            def __init__(self):
                super().__init__()

            def run(self):
                try:
                    fn()
                except Exception:
                    pass

        return R()
    except Exception:
        return fn


# ==================== 本地自测(独立跑用,客户端不执行这段) ====================
if __name__ == "__main__":
    import sys
    sp = Spider()
    sp.init(sys.argv[1] if len(sys.argv) > 1 else "")

    hc = sp.homeContent()
    print("[home] 分类数 = %d" % len(hc["class"]))
    for c in hc["class"][:6]:
        print("    ", c["type_id"], c["type_name"])

    for tid in ("latest", "hot"):
        r = sp.categoryContent(tid, 1, False, None)
        print("[cat %-6s] %d 条 / pagecount=%s  action=%s" %
              (tid, len(r["list"]), r["pagecount"],
               (r["list"][0].get("action") if r["list"] else "-")))
        for it in r["list"][:2]:
            print("      -", it["vod_name"][:50], "|", (it["vod_pic"] or "")[:70])
            print("        id:", it["vod_id"])

    big = hc["class"][2]["type_id"]
    t0 = time.time()
    r = sp.categoryContent(big, 1, False, None)
    print("[大分类 %s] 小分类 %d 个, %.2fs" % (big, len(r["list"]), time.time() - t0))
    for it in r["list"][:8]:
        print("      -", it["vod_name"][:30], "|", it.get("vod_remarks"), "|", it["vod_id"])

    wall = {"list": []}
    if len(r["list"]) > 1:
        sub = r["list"][2]["vod_id"]
        t0 = time.time()
        wall = sp.categoryContent(sub, 1, False, None)
        print("[小分类 %s] 图片墙 %d 条, %.2fs" % (sub, len(wall["list"]), time.time() - t0))
        if wall["list"]:
            print("      首条:", wall["list"][0]["vod_name"][:46], "| id:", wall["list"][0]["vod_id"])

    # 看图队列:从当前这列连拉两组,验证"滑到底自动接下一组"
    if wall["list"]:
        v = wall["list"][0]["vod_id"]
        parts = v.split("|")
        q = sp._q_get(parts[1])
        sp._vm = q
        t0 = time.time()
        a, e = sp._vm_next()
        b, e2 = sp._vm_next()
        print("[看图队列] 第一组 %d 张 / 第二组 %d 张, %.2fs, 到底=%s"
              % (len(a), len(b), time.time() - t0, e2))
        if a:
            print("      首图:", a[0]["u"][:100])
            print("      标题:", a[0]["w"])

    r = sp.searchContent("杨晨晨", False, "1")
    print("[search] %d 条" % len(r["list"]))

    tv, imgs, link = sp._post_imgs(v if wall["list"] else "p:0")
    print("[图集] %s | %d 张 | %s" % (tv[:40], len(imgs), link[:60]))

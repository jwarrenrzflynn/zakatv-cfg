#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ZakaTV 配置备用线 · 同步机器人
================================
干的事:定时把 CF 站上的 tvbox 配置(ZakaTV.json + 爬虫 jar)同步到 git 仓库,
并且把配置里所有指向 CF 的资源引用改写成 git 地址 —— 这样 CF 限流/挂掉时,
备用线是一条完全自洽的线,不碰 CF 也能跑。

纯标准库实现(不需要 git 二进制),用 GitHub Git Data 接口推送,单文件 1.2MB 也稳。

用法:
    python3 bot.py            # 常驻,按 interval 分钟轮询
    python3 bot.py --once     # 只跑一轮(测试/手工触发)
    python3 bot.py --check    # 只比对,不推送
"""
import base64
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CFG_PATH = os.path.join(HERE, "config.json")

DEFAULTS = {
    "token": "",
    "owner": "jwarrenrzflynn",
    "repo": "zakatv-cfg",
    "branch": "main",
    # CF 侧配置源,按顺序试,第一个拿到有效配置就用它
    "sources": [
        "https://tv.ystv.top/files/ZakaTV.json",
        "https://admin.ystv.top/files/ZakaTV.json",
        "https://ztv2.ystv.top/files/ZakaTV.json",
    ],
    # CF 侧爬虫包(站方伪装成 png 的那个)
    "jar_sources": [
        "https://tv.ystv.top/files/ai-zhineng.png",
        "https://admin.ystv.top/files/ai-zhineng.png",
        "https://ztv2.ystv.top/files/ai-zhineng.png",
    ],
    "mirrors": [
        {"file": "ZakaTV.json", "prefix": "https://ghfast.top/https://raw.githubusercontent.com/{o}/{r}/{b}/"},
        {"file": "ZakaTV.raw.json", "prefix": "https://raw.githubusercontent.com/{o}/{r}/{b}/"},
        {"file": "ZakaTV.jsdelivr.json", "prefix": "https://cdn.jsdelivr.net/gh/{o}/{r}@{b}/"},
    ],
    "interval_minutes": 15,
    "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36",
    "timeout": 30,
}


def log(*a):
    print(time.strftime("[%Y-%m-%d %H:%M:%S]"), *a, flush=True)


def load_cfg():
    cfg = dict(DEFAULTS)
    if os.path.exists(CFG_PATH):
        with open(CFG_PATH, encoding="utf-8") as f:
            cfg.update(json.load(f))
    cfg["token"] = cfg.get("token") or os.environ.get("GH_TOKEN", "")
    return cfg


def md5b(b):
    return hashlib.md5(b).hexdigest()


def http_get(url, timeout=30, ua=None, maxbytes=None):
    """返回 (status, bytes)。任何异常都吞掉返回 (None, 原因)。"""
    req = urllib.request.Request(url, headers={
        "User-Agent": ua or DEFAULTS["ua"],
        "Accept": "*/*",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read() if maxbytes is None else r.read(maxbytes)
            return r.status, data
    except urllib.error.HTTPError as e:
        body = b""
        try:
            body = e.read(2048)
        except Exception:
            pass
        return e.code, body
    except Exception as e:  # 网络层
        return None, str(e).encode()


def gh(cfg, method, path, body=None, timeout=60):
    url = "https://api.github.com" + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": "Bearer " + cfg["token"],
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "zakatv-cfg-sync",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except Exception:
            return e.code, {}
    except Exception as e:
        return None, {"error": str(e)}


# ---------------------------------------------------------------- 抓 CF 侧

def fetch_config(cfg):
    """抓 CF 上的主配置。限流页 / HTML / 坏 JSON 一律当失败。"""
    for u in cfg["sources"]:
        st, body = http_get(u, cfg["timeout"], cfg["ua"], maxbytes=3 << 20)
        if st != 200:
            log(f"   源 {u} -> HTTP {st},换下一个")
            continue
        if body.lstrip()[:1] not in (b"{",):
            log(f"   源 {u} 返回的不是 JSON(限流页),换下一个")
            continue
        try:
            obj = json.loads(body.decode("utf-8"))
        except Exception as e:
            log(f"   源 {u} JSON 解析失败: {e}")
            continue
        if not obj.get("sites"):
            log(f"   源 {u} 站点列表为空,换下一个")
            continue
        return u, body, obj
    return None, None, None


def fetch_jar(cfg, want_md5=None):
    for u in cfg["jar_sources"]:
        st, body = http_get(u, cfg["timeout"], cfg["ua"], maxbytes=8 << 20)
        if st != 200 or not body:
            log(f"   jar 源 {u} -> HTTP {st},换下一个")
            continue
        if not body.startswith(b"PK"):
            log(f"   jar 源 {u} 不是 zip(jar) 头,跳过")
            continue
        if want_md5 and md5b(body) != want_md5:
            log(f"   jar 源 {u} 指纹不符(线上刚更新?),跳过")
            continue
        return u, body
    return None, None


# ---------------------------------------------------------------- 造包

def rewrite(cfg, raw_cfg, jar_md5, prefix):
    obj = json.loads(raw_cfg.decode("utf-8"))
    obj["spider"] = f"{prefix}files/ai-zhineng.jar;md5;{jar_md5}"

    def walk(n):
        if isinstance(n, dict):
            return {k: walk(v) for k, v in n.items()}
        if isinstance(n, list):
            return [walk(v) for v in n]
        if isinstance(n, str):
            for host in ("https://tv.ystv.top/files/", "http://tv.ystv.top/files/"):
                if host in n:
                    n = n.replace(host, prefix + "files/")
            return n
        return n

    obj = walk(obj)
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def build_files(cfg, raw_cfg, jar):
    obj = json.loads(raw_cfg.decode("utf-8"))
    m = re.search(r";md5;([0-9a-f]{32})", obj.get("spider", "") or "")
    jar_md5 = m.group(1) if m else md5b(jar)
    files = {}
    for mir in cfg["mirrors"]:
        prefix = mir["prefix"].format(o=cfg["owner"], r=cfg["repo"], b=cfg["branch"])
        files[mir["file"]] = rewrite(cfg, raw_cfg, jar_md5, prefix)
    files["ZakaTV.origin.json"] = raw_cfg
    files["files/ai-zhineng.jar"] = jar
    files["files/ai-zhineng.png"] = jar
    return files, jar_md5


def make_manifest(cfg, files, jar_md5, src_url, src_md5, old=None):
    obj = json.loads(files["ZakaTV.json"].decode("utf-8"))
    man = {
        "updated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "owner": cfg["owner"], "repo": cfg["repo"], "branch": cfg["branch"],
        "links": {m["file"]: {"mirror": m["prefix"].format(o=cfg["owner"], r=cfg["repo"], b=cfg["branch"]),
                              "bytes": len(files[m["file"]])} for m in cfg["mirrors"]},
        "assets": {k: {"md5": md5b(v), "bytes": len(v)}
                   for k, v in files.items() if k.startswith("files/")},
        "config": {"sites": len(obj.get("sites", [])), "lives": len(obj.get("lives", [])),
                   "parses": len(obj.get("parses", [])), "md5": src_md5},
        "source": src_url,
        "sync_count": (old or {}).get("sync_count", 0) + 1,
    }
    files["manifest.json"] = json.dumps(man, ensure_ascii=False, indent=2).encode("utf-8")
    return man


# ---------------------------------------------------------------- 推 git

def remote_manifest(cfg):
    """读仓库里现有 manifest(带时间戳破缓存)。"""
    st, body = http_get(
        f"https://raw.githubusercontent.com/{cfg['owner']}/{cfg['repo']}/{cfg['branch']}"
        f"/manifest.json?t={int(time.time())}", cfg["timeout"], maxbytes=1 << 20)
    if st == 200 and body and body.lstrip()[:1] == b"{":
        try:
            return json.loads(body.decode("utf-8"))
        except Exception:
            return None
    return None


def push(cfg, files, changed, message):
    """用 Git Data 接口一次性提交所有变更。"""
    owner, repo, br = cfg["owner"], cfg["repo"], cfg["branch"]

    st, ref = gh(cfg, "GET", f"/repos/{owner}/{repo}/git/ref/heads/{br}")
    if st == 404:  # 空仓库,先建一个根提交
        st2, blob = gh(cfg, "POST", f"/repos/{owner}/{repo}/git/blobs",
                       {"content": base64.b64encode(files["manifest.json"]).decode(), "encoding": "base64"})
        st3, tree = gh(cfg, "POST", f"/repos/{owner}/{repo}/git/trees",
                       {"tree": [{"path": "manifest.json", "mode": "100644", "type": "blob", "sha": blob["sha"]}]})
        st4, com = gh(cfg, "POST", f"/repos/{owner}/{repo}/git/commits",
                      {"message": message, "tree": tree["sha"]})
        st5, _ = gh(cfg, "POST", f"/repos/{owner}/{repo}/git/refs",
                    {"ref": f"refs/heads/{br}", "sha": com["sha"]})
        if not (st2 == st3 == st4 == 201 and st5 == 201):
            return False, f"初始化失败 {st2}/{st3}/{st4}/{st5}"
        st, ref = gh(cfg, "GET", f"/repos/{owner}/{repo}/git/ref/heads/{br}")
    if st != 200:
        return False, f"取分支失败 HTTP {st}: {ref}"

    head = ref["object"]["sha"]
    st, com = gh(cfg, "GET", f"/repos/{owner}/{repo}/git/commits/{head}")
    if st != 200:
        return False, f"取提交失败 HTTP {st}"
    base_tree = com["tree"]["sha"]

    entries = []
    for path in changed:
        content = files[path]
        st, blob = gh(cfg, "POST", f"/repos/{owner}/{repo}/git/blobs",
                      {"content": base64.b64encode(content).decode(), "encoding": "base64"})
        if st != 201:
            return False, f"blob 失败 {path} HTTP {st}: {str(blob)[:200]}"
        entries.append({"path": path, "mode": "100644", "type": "blob", "sha": blob["sha"]})

    st, tree = gh(cfg, "POST", f"/repos/{owner}/{repo}/git/trees",
                  {"base_tree": base_tree, "tree": entries})
    if st != 201:
        return False, f"tree 失败 HTTP {st}"
    st, newc = gh(cfg, "POST", f"/repos/{owner}/{repo}/git/commits",
                  {"message": message, "tree": tree["sha"], "parents": [head]})
    if st != 201:
        return False, f"commit 失败 HTTP {st}"
    st, r = gh(cfg, "PATCH", f"/repos/{owner}/{repo}/git/refs/heads/{br}", {"sha": newc["sha"]})
    if st != 200:
        return False, f"更新分支失败 HTTP {st}"
    return True, newc["sha"][:8]


# ---------------------------------------------------------------- 一轮

def one_round(cfg, dry=False):
    log("— 轮询开始 —")
    src_url, raw_cfg, obj = fetch_config(cfg)
    if not raw_cfg:
        return "cf_down", "CF 侧所有源都拿不到配置(限流/故障),本轮保持现有内容不动"

    src_md5 = md5b(raw_cfg)
    rman = remote_manifest(cfg)
    if rman and rman.get("config", {}).get("md5") == src_md5:
        # 配置没变,再确认一下 jar 也在
        log(f"   配置未变(md5 {src_md5[:8]}),无需推送")
        return "nochange", "配置未变"

    m = re.search(r";md5;([0-9a-f]{32})", obj.get("spider", "") or "")
    want = m.group(1) if m else None
    jar_url, jar = fetch_jar(cfg, want)
    if not jar:
        # 配置变了但 jar 拿不到(限流)。不推半成品,等下一轮
        return "partial", "拿到新配置但爬虫包取不到(CF 限流),为避免推出半成品,本轮不推"

    files, jar_md5 = build_files(cfg, raw_cfg, jar)
    man = make_manifest(cfg, files, jar_md5, src_url, src_md5, rman)

    # 只推真正变了的文件(jar 没变就不重复推 1.2MB)
    changed = []
    old_assets = (rman or {}).get("assets", {})
    for path, content in files.items():
        if path.startswith("files/"):
            if old_assets.get(path, {}).get("md5") != md5b(content):
                changed.append(path)
        else:
            changed.append(path)
    if not changed:
        return "nochange", "无差异"

    if dry:
        log(f"   [dry-run] 将推送 {len(changed)} 个文件: {changed}")
        return "dryrun", f"将推送 {changed}"

    msg = (f"sync: 配置更新 sites={man['config']['sites']} "
           f"md5={src_md5[:8]} jar={jar_md5[:8]} @{man['updated_utc']}")
    ok, info = push(cfg, files, changed, msg)
    if ok:
        log(f"   ✅ 已推送 {len(changed)} 个文件 -> {info}  ({', '.join(changed)})")
        return "pushed", f"{len(changed)} 个文件 -> {info}"
    log(f"   ❌ 推送失败: {info}")
    return "error", info


def main():
    cfg = load_cfg()
    if not cfg["token"]:
        log("缺少 token:请在 config.json 填 token,或设 GH_TOKEN 环境变量")
        sys.exit(2)
    args = sys.argv[1:]

    if "--check" in args:
        st, msg = one_round(cfg, dry=True)
        log(f"结果: {st} / {msg}")
        return
    if "--once" in args:
        st, msg = one_round(cfg)
        log(f"结果: {st} / {msg}")
        return

    interval = max(1, int(cfg["interval_minutes"])) * 60
    log(f"同步机器人启动: {cfg['owner']}/{cfg['repo']}@{cfg['branch']},"
        f"间隔 {cfg['interval_minutes']} 分钟")
    fails = 0
    while True:
        try:
            st, msg = one_round(cfg)
            log(f"   结果: {st} / {msg}")
            fails = 0 if st in ("pushed", "nochange") else fails + 1
        except Exception as e:
            fails += 1
            log(f"   异常: {type(e).__name__}: {e}")
        wait = interval if fails == 0 else min(interval * (2 ** min(fails, 4)), 3600)
        if fails:
            log(f"   连续失败 {fails} 次,{wait // 60} 分钟后重试")
        time.sleep(wait)


if __name__ == "__main__":
    main()

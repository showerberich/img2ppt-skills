#!/usr/bin/env python3
"""img2ppt 命令行客户端：把图片/PDF 交给 img2ppt 服务，拿回可编辑的 PPTX。

给**第三方工具**用的，所以刻意只依赖 Python 3 标准库 —— 别人的 agent 里未必装得上
requests，而 urllib 一定有。这里也不碰服务端的任何内部实现，只走公开的 HTTP 接口。

用法：
    export IMG2PPT_TOKEN=ppt_xxx          # 令牌（见 SKILL.md 怎么换）
    python3 img2ppt.py me                 # 余额
    python3 img2ppt.py convert 海报.png     # 转 → 海报.pptx
    python3 img2ppt.py convert 讲义.pdf --pages 5
    python3 img2ppt.py status 12345

退出码：0 成功 / 2 令牌无效 / 3 积分不够 / 4 转换失败 / 5 超时 / 6 用法或环境不对
"""
import argparse
import json
import mimetypes
import os
import secrets
import sys
import time
import urllib.error
import urllib.request

DEFAULT_API = "https://image2ppt.asia"
POLL_SECONDS = 20          # 服务端每 5 秒扫一次作业目录，20 秒问一次足够且不打扰别人
DEFAULT_TIMEOUT = 3600     # 实测单张 20–40 分钟，默认给到 1 小时

EXIT_OK, EXIT_AUTH, EXIT_MONEY, EXIT_FAILED, EXIT_TIMEOUT, EXIT_USAGE = 0, 2, 3, 4, 5, 6


class ApiError(Exception):
    def __init__(self, code: int, detail: str, body: dict | None = None):
        super().__init__(detail)
        self.code, self.detail, self.body = code, detail, body or {}


def _base() -> str:
    return (os.environ.get("IMG2PPT_API") or DEFAULT_API).rstrip("/")


def _token() -> str:
    tok = (os.environ.get("IMG2PPT_TOKEN") or "").strip()
    if not tok:
        die(EXIT_USAGE, "没有令牌：先 export IMG2PPT_TOKEN=ppt_xxx\n"
                        "（怎么换令牌见 SKILL.md，一行 curl 的事）")
    return tok


def die(code: int, msg: str) -> None:
    print(msg, file=sys.stderr)
    sys.exit(code)


def _request(method: str, path: str, *, token: str | None = None, body=None,
             ctype: str | None = None, stream: bool = False):
    """发一次请求。**只管把失败变成异常，不做任何决定** —— 因为「连不上」在一次
    20 分钟的轮询里只是网络抖了一下（该重试），在一次 me 调用里就是真连不上（该报错），
    这两件事只有调用方知道。"""
    req = urllib.request.Request(_base() + path, data=body, method=method)
    if token:
        req.add_header("Authorization", "Bearer " + token)
    if ctype:
        req.add_header("Content-Type", ctype)
    try:
        r = urllib.request.urlopen(req, timeout=120)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            payload = json.loads(raw)
            detail = (payload.get("detail") or payload.get("msg")
                      or raw[:200].decode("utf-8", "replace"))
        except Exception:  # noqa: BLE001
            payload, detail = {}, raw[:200].decode("utf-8", "replace")
        raise ApiError(e.code, str(detail), payload if isinstance(payload, dict) else {}) from e
    except urllib.error.URLError as e:
        raise ApiError(0, f"连不上 {_base()}：{e.reason}") from e
    if stream:
        return r
    raw = r.read()
    if r.headers.get("content-type", "").startswith("application/json"):
        return json.loads(raw)
    return raw


def _auth_or_money(e: ApiError) -> None:
    """401/402 是全局语义，走到哪儿都是同一句话：令牌不行 / 钱不够。

    充值地址优先用服务端给的那个（服务端最清楚站点在哪），拿不到才退回 base。
    """
    if e.code == 401:
        die(EXIT_AUTH, f"令牌无效或已吊销（{e.detail}）。\n"
                       f"到 {_base()}/ 重新换一枚，或先检查 IMG2PPT_TOKEN。")
    if e.code == 402:
        pay = f"（{e.body.get('credits')} 积分）" if e.body.get("credits") is not None else ""
        die(EXIT_MONEY, f"积分不够{pay}：{e.detail}\n"
                        f"请到 {e.body.get('recharge_url') or _base() + '/'} 充值后重试"
                        f"（微信/支付宝，充完直接就能用，不用换令牌）。")


def api(method: str, path: str, **kw) -> dict:
    """一次性调用（查余额、提交、查状态）：任何失败都当场说清楚并退出。"""
    try:
        return _request(method, path, **kw)
    except ApiError as e:
        _auth_or_money(e)
        die(EXIT_USAGE, f"请求失败（HTTP {e.code}）：{e.detail}")


def _multipart(fields: dict, path: str) -> tuple[bytes, str]:
    """手搓 multipart/form-data —— 标准库里没有现成的，为这点事引入依赖不划算。"""
    boundary = "----img2ppt" + secrets.token_hex(16)
    name = os.path.basename(path)
    ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
    if name.lower().endswith(".pdf"):
        ctype = "application/pdf"
    with open(path, "rb") as f:
        blob = f.read()
    buf = bytearray()
    for k, v in fields.items():
        buf += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n"
                f"{v}\r\n").encode("utf-8")
    buf += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
            f"filename=\"{name}\"\r\nContent-Type: {ctype}\r\n\r\n").encode("utf-8")
    buf += blob + b"\r\n"
    buf += f"--{boundary}--\r\n".encode("utf-8")
    return bytes(buf), f"multipart/form-data; boundary={boundary}"


def cmd_me(_args) -> int:
    d = api("GET", "/api/v1/me", token=_token())
    print(f"{d['email']} · 剩余 {d['credits']} 积分")
    if d["credits"] <= 0:
        print(f"⚠️ 没积分了，转换会被拒。充值：{d.get('recharge_url') or _base() + '/'}")
    return EXIT_OK


def cmd_pricing(_args) -> int:
    d = api("GET", "/api/v1/pricing", token=_token())
    print(json.dumps(d, ensure_ascii=False, indent=2))
    return EXIT_OK


def cmd_convert(args) -> int:
    src = args.image
    if not os.path.isfile(src):
        die(EXIT_USAGE, f"找不到文件：{src}")
    token = _token()
    if not args.pages:
        cmd_me(args)                     # 顺手报一下余额，别让用户扣完才知道

    fields = {"ratio": args.ratio, "confirm_pages": str(args.pages or "")}
    body, ctype = _multipart(fields, src)
    d = api("POST", "/api/v1/convert", token=token, body=body, ctype=ctype)

    if d.get("need_confirm"):
        pages = _confirm_pages(d, args)
        fields["confirm_pages"] = str(pages)
        body, ctype = _multipart(fields, src)
        d = api("POST", "/api/v1/convert", token=token, body=body, ctype=ctype)

    jid = str(d["job_id"])
    print(f"作业 #{jid} 已提交（本次扣 {d.get('cost', d.get('pages', 1))} 积分，"
          f"余额 {d.get('credits')}）")
    return _wait_and_fetch(jid, token, src, args)


def _confirm_pages(d: dict, args) -> int:
    """多页 PDF 先确认页数：静默扣一大笔是最伤信任的事，网页和这里一个口径。"""
    msg = d.get("msg") or f"共 {d.get('total_pages')} 页，要转几页？"
    if args.pages:
        return int(args.pages)
    if args.yes:
        n = int(d.get("pages_to_convert") or d.get("total_pages") or 1)
        print(f"{msg} → --yes 直接按 {n} 页走")
        return n
    if sys.stdin.isatty():
        ans = input(f"{msg}\n输入要转的页数（回车=按推荐值 "
                    f"{d.get('pages_to_convert')}）: ").strip()
        return int(ans) if ans.isdigit() else int(d.get("pages_to_convert") or 1)
    die(EXIT_USAGE, f"{msg}\n非交互环境下请显式给 --pages N（要转几页）或 --yes（接受推荐值）。")


def _wait_and_fetch(jid: str, token: str, src: str, args) -> int:
    t0 = time.time()
    last_stage = ""
    while True:
        if time.time() - t0 > args.timeout:
            die(EXIT_TIMEOUT, f"等太久了（超过 {args.timeout // 60} 分钟）。\n"
                              f"作业还在服务端继续跑，稍后用 status {jid} 查，"
                              f"跑完再下：convert 不会重跑，别重新提交（会再扣一次分）。")
        try:
            job = _request("GET", f"/api/v1/jobs/{jid}", token=token)["job"]
        except ApiError as e:
            _auth_or_money(e)                      # 令牌/钱的问题，重试一万次也没用
            if e.code in (0, 500, 502, 503, 504) or e.code == 429:
                # 网络抖一下、服务端重启、限流 —— 都只当这一轮没问到。
                # 让一次 20 分钟的等待因为一个丢包而崩掉是不可接受的。
                time.sleep(POLL_SECONDS)
                continue
            die(EXIT_USAGE, f"查作业失败（HTTP {e.code}）：{e.detail}")
        stage = job.get("stage") or ""
        elapsed = _fmt(time.time() - t0)
        if stage and stage != last_stage:
            last_stage = stage
            pv = job.get("preview")
            print(f"  [{elapsed}] {stage}" + (f"（第 {pv} 版渲染图）" if pv else ""), flush=True)

        if job.get("status") == "ok" or job.get("has_file"):
            # 默认落在**原图旁边**同名 .pptx：调用方给的是绝对路径，产物就该在它边上，
            # 而不是落在某个 agent 自己也说不清的当前目录里。
            out = args.out or (os.path.splitext(src)[0] + ".pptx")
            _download(jid, token, out)
            ver = job.get("round") or job.get("preview") or 0
            print(f"成品已保存：{os.path.abspath(out)}（{elapsed}"
                  + (f" · 第 {ver} 版" if ver else "") + "）")
            return EXIT_OK
        if job.get("status") == "failed":
            die(EXIT_FAILED, f"转换失败：{job.get('error') or '服务端没有给出原因'}\n"
                             f"积分已自动退回；可以在站上重试，或换一张更清晰的图。")
        time.sleep(POLL_SECONDS)


def _download(jid: str, token: str, out: str) -> None:
    try:
        r = _request("GET", f"/api/v1/jobs/{jid}/pptx", token=token, stream=True)
    except ApiError as e:
        _auth_or_money(e)
        die(EXIT_FAILED, f"下不到成品（HTTP {e.code}）：{e.detail}")
    tmp = out + ".part"
    try:
        with open(tmp, "wb") as f:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
        os.replace(tmp, out)          # 半截文件不冒充成品
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def cmd_status(args) -> int:
    job = api("GET", f"/api/v1/jobs/{args.job_id}", token=_token())["job"]
    print(f"#{job['id']} {job['filename']} · {job['status']}"
          + (f" · {job['stage']}" if job.get("stage") else ""))
    if job.get("preview"):
        print(f"  中间稿：第 {job['preview']} 版渲染图"
              + (f"，可下载的是第 {job['round']} 版" if job.get("round") else ""))
    if job.get("has_file"):
        print(f"  成品已就绪（{_base()}/api/v1/jobs/{job['id']}/pptx）")
    return EXIT_OK


def _fmt(sec: float) -> str:
    sec = int(sec)
    return f"{sec // 60} 分 {sec % 60} 秒" if sec >= 60 else f"{sec} 秒"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="把图片/PDF 转成可编辑 PPT（走 img2ppt 的 HTTP API）")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("me", help="看余额").set_defaults(fn=cmd_me)
    sub.add_parser("pricing", help="看计价与限制").set_defaults(fn=cmd_pricing)

    c = sub.add_parser("convert", help="提交转换并等到成品")
    c.add_argument("image", help="图片或 PDF 路径")
    c.add_argument("-o", "--out", help="成品保存到哪儿（默认与原图同名 .pptx）")
    c.add_argument("--ratio", default="auto", choices=["auto", "16:9", "4:3"],
                   help="页面比例，默认跟随原图")
    c.add_argument("--pages", type=int, help="多页 PDF 只转前 N 页（按页扣积分）")
    c.add_argument("--yes", action="store_true",
                   help="多页 PDF 不问，直接按服务端推荐页数转")
    c.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT,
                   help=f"最多等多少秒（默认 {DEFAULT_TIMEOUT}）")
    c.set_defaults(fn=cmd_convert)

    s = sub.add_parser("status", help="查一个作业")
    s.add_argument("job_id")
    s.set_defaults(fn=cmd_status)

    args = p.parse_args(argv)
    try:
        return args.fn(args)
    except KeyboardInterrupt:
        print("\n已中断。作业在服务端照跑，用 status <job_id> 还能查到它。", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())

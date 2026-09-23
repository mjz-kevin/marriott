#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI SDLC 安全闸门 · Atlassian（Confluence / Jira）写操作确认 hook 的核心逻辑。

用途
----
无论用哪个模型（含 grok 这类"指令遵循较弱、常常不问就直接上传"的模型），凡是要往
Confluence / Jira 做「创建 / 修改 / 评论 / 状态流转 / 建链 / 记工时」等写操作，都必须先经
过用户明确批准，才允许放行。只读的 get / search 一律放行，不打扰。

为什么用 deny 做闸门
--------------------
Cursor 当前版本里，hook 返回的 permission 只有 "deny" 会被可靠强制执行；"ask" / "allow"
可能被忽略（尤其对不主动发问的模型 ask 拦不住）。因此本闸门用「先 deny、经用户批准后
再放行」的模式：模型绕不过——它顶多把内容念给用户，真正的放行动作发生在文件系统、由
用户手动执行，模型碰不到，无法伪造。

拦截的两条写入路径
------------------
Confluence / Jira 的写入在本工具链里有两条路径，本脚本都拦：
  A) Atlassian MCP 工具（beforeMCPExecution）：createConfluencePage / createJiraIssue /
     editJiraIssue / transitionJiraIssue / 各类评论 / 建链 / 记工时等。
  B) 发布类 Skill 的 REST 上传脚本（beforeShellExecution）：prd-publish / tech-solution-publish
     / user-story-publish 三个 skill 用 `scripts/upload_confluence_v2.py` 走 Confluence REST
     直接建/改页面（不经 MCP）。凡是真正会写库的命令（未带 --dry-run / --check-env）都拦。

工作流程
--------
本脚本可被注册为 `beforeMCPExecution` 和 `beforeShellExecution` 两个 hook（用同一份逻辑）：
1. 从 stdin 读入 Cursor 传来的 JSON：
   - MCP 事件：含 mcp_server_name / tool_name / tool_input。
   - Shell 事件：含 command（待执行的完整命令行）。
2. 只对【Atlassian 写操作】（MCP 写工具）或【upload_confluence_v2.py 正式上传】生效；
   其余（MCP 只读、别的 server、别的 shell 命令、dry-run 预检）一律直接 allow，不打扰。
3. 计算本次写操作的「内容指纹」（关键内容字段/命令行关键参数的哈希，取前 10 位为操作码）。
4. 看放行目录 ~/.cursor/ai-sdlc-guard/approved/<操作码> 是否存在且未过期：
   - 存在 → allow，并用后即焚删除该放行文件（一次批准只放行一次）。
   - 不存在 → deny，同时把「将要执行什么 + 操作码 + 一行批准命令」写进 pending 记录，
     并通过 user_message 展示给用户、通过 agent_message 指示 agent 先把内容念给用户、
     等用户批准后【原样重试同一调用】（不要改参数、不要伪造任何确认信息）。

用户批准方式（模型碰不到）
--------------------------
用户在 user_message 里会看到一行可复制的批准命令，例如：
    python3 ~/.cursor/hooks/guard_atlassian.py --approve <操作码>
复制到终端执行即批准下一次同内容重试。也可用无参的 --approve-next 批准"下一个"写操作
（不校验指纹，适合内容较长懒得比对操作码时）。

跨平台
------
纯 Python 标准库实现，mac / windows 共用本文件。两个平台各自用轻量启动器（.sh / .cmd）
调用本脚本，hooks.json 里按平台指向对应启动器。

退出码
------
始终以 0 退出并在 stdout 打印 JSON 决策；解析失败等异常按「fail-safe = deny」处理
（宁可挡住也不误放行），并在 agent_message 里说明原因。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import sys
import time
from pathlib import Path

# ---- 常量 ----
GUARD_HOME = Path(os.environ.get("AI_SDLC_GUARD_HOME", str(Path.home() / ".cursor" / "ai-sdlc-guard")))
APPROVED_DIR = GUARD_HOME / "approved"
PENDING_DIR = GUARD_HOME / "pending"
APPROVE_NEXT_FLAG = GUARD_HOME / "APPROVE_NEXT"      # 无差别放行下一个写操作的一次性标记
APPROVAL_TTL_SEC = int(os.environ.get("AI_SDLC_GUARD_TTL", "1800"))  # 批准有效期，默认 30 分钟

# 被视为 Atlassian 的 MCP server 名（mcp.json 里的 key）。可用环境变量扩展。
ATLASSIAN_SERVER_HINTS = ("atlassian",)
_extra = os.environ.get("AI_SDLC_GUARD_SERVERS", "").strip()
if _extra:
    ATLASSIAN_SERVER_HINTS = ATLASSIAN_SERVER_HINTS + tuple(
        s.strip().lower() for s in _extra.split(",") if s.strip()
    )

# 需要拦截的【写操作】工具名（精确匹配，小写比较）。覆盖创建/修改/评论/流转/建链/工时。
# 只读工具（get* / search* / list* / lookup* / fetch 等）不在此列，一律放行。
WRITE_TOOLS = {
    # --- Confluence 写 ---
    "createconfluencepage",
    "updateconfluencepage",
    "deleteconfluencepage",
    "createconfluencefootercomment",
    "createconfluenceinlinecomment",
    # --- Jira 写 ---
    "createjiraissue",
    "editjiraissue",
    "deletejiraissue",
    "transitionjiraissue",
    "addcommenttojiraissue",
    "addworklogtojiraissue",
    "createissuelink",
    "deleteissuelink",
    # --- 通用兜底：任何以这些前缀开头的工具都视为写操作 ---
}
# 前缀兜底：只要工具名以下列动词开头，且属于 Atlassian server，也当写操作拦（防止漏配新工具）。
WRITE_PREFIXES = ("create", "update", "edit", "delete", "add", "transition", "move", "set", "remove", "archive", "publish")

# ---- Shell 路径：发布类 Skill 的 REST 上传脚本（不经 MCP，直接写 Confluence）----
# prd-publish / tech-solution-publish / user-story-publish 三个 skill 都用它。
# 命令行里出现该脚本名即视为「可能的写操作」，再看是否真的会写库（非 dry-run）。
SHELL_WRITE_SCRIPTS = ("upload_confluence_v2.py",)
# 额外可通过环境变量补充需要拦截的脚本名（逗号分隔）。
_extra_scripts = os.environ.get("AI_SDLC_GUARD_SHELL_SCRIPTS", "").strip()
if _extra_scripts:
    SHELL_WRITE_SCRIPTS = SHELL_WRITE_SCRIPTS + tuple(
        s.strip() for s in _extra_scripts.split(",") if s.strip()
    )
# 命令行里带这些标志表示「只预检、不写库」，放行不打扰。
DRY_RUN_FLAGS = ("--dry-run", "--check-env")
# 从上传命令行里抽取用于生成指纹/摘要的参数。
SHELL_CONTENT_FLAGS = ("--md", "--title", "--title-key", "--space", "--root",
                       "--epic", "--kind", "--parent", "--initiative")

# 从各写操作里抽取「关键内容字段」，用于生成稳定的内容指纹（不同内容 → 不同操作码）。
CONTENT_FIELDS = (
    "title", "body", "summary", "description", "commentBody", "comment",
    "spaceId", "projectKey", "issueIdOrKey", "issueKey", "cloudId",
    "transition", "status", "worklog", "timeSpent", "type",
)


def _now() -> float:
    return time.time()


def _read_stdin_json() -> dict:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    return json.loads(raw)


def _parse_tool_input(tool_input) -> dict:
    """tool_input 在 beforeMCPExecution 里是 JSON 字符串；也兼容已是 dict 的情况。"""
    if isinstance(tool_input, dict):
        return tool_input
    if isinstance(tool_input, str) and tool_input.strip():
        try:
            v = json.loads(tool_input)
            return v if isinstance(v, dict) else {"_raw": tool_input}
        except Exception:
            return {"_raw": tool_input}
    return {}


def _is_atlassian(server_name: str, command: str) -> bool:
    s = (server_name or "").lower()
    if any(h in s for h in ATLASSIAN_SERVER_HINTS):
        return True
    # server 名拿不到时，用启动命令兜底判断
    c = (command or "").lower()
    return "atlassian" in c


def _is_write_tool(tool_name: str) -> bool:
    t = (tool_name or "").lower()
    if t in WRITE_TOOLS:
        return True
    return any(t.startswith(p) for p in WRITE_PREFIXES)


def _fingerprint(server_name: str, tool_name: str, tool_input: dict) -> str:
    """对 server + tool + 关键内容字段做哈希，取前 10 位十六进制作为操作码。"""
    h = hashlib.sha256()
    h.update((server_name or "").lower().encode("utf-8"))
    h.update(b"|")
    h.update((tool_name or "").lower().encode("utf-8"))
    for f in CONTENT_FIELDS:
        if f in tool_input and tool_input[f] is not None:
            h.update(b"|")
            h.update(f.encode("utf-8"))
            h.update(b"=")
            h.update(json.dumps(tool_input[f], ensure_ascii=False, sort_keys=True).encode("utf-8"))
    return h.hexdigest()[:10]


# ---- Shell 命令解析（upload_confluence_v2.py 等 REST 上传脚本）----

def _tokenize_command(command: str) -> list[str]:
    """把命令行拆成 token。优先用 shlex（POSIX），失败则退化为空白切分。"""
    try:
        return shlex.split(command, posix=True)
    except Exception:
        return command.split()


def _shell_hits_write_script(command: str) -> str | None:
    """命令行是否调用了需拦截的上传脚本；命中则返回脚本名，否则 None。"""
    c = command or ""
    for name in SHELL_WRITE_SCRIPTS:
        # 用词边界匹配脚本名，兼容各种路径分隔符（/ 或 \）与引号
        if re.search(r"(^|[\s/\\\"'=]) *" + re.escape(name), c) or name in c:
            return name
    return None


def _shell_is_dry_run(tokens: list[str]) -> bool:
    lowered = [t.lower() for t in tokens]
    return any(flag in lowered for flag in DRY_RUN_FLAGS)


def _parse_flag_values(tokens: list[str]) -> dict:
    """从 token 里抽取 --flag value / --flag=value 形式的关注参数值。"""
    out: dict = {}
    i = 0
    n = len(tokens)
    wanted = set(SHELL_CONTENT_FLAGS)
    while i < n:
        tok = tokens[i]
        if tok in wanted:
            val = tokens[i + 1] if i + 1 < n else ""
            out[tok] = val
            i += 2
            continue
        if tok.startswith("--") and "=" in tok:
            k, v = tok.split("=", 1)
            if k in wanted:
                out[k] = v
        i += 1
    return out


def _shell_fingerprint(script_name: str, flag_values: dict) -> str:
    """对上传脚本名 + 关键参数做哈希，取前 10 位作为操作码。"""
    h = hashlib.sha256()
    h.update(b"shell|")
    h.update(script_name.encode("utf-8"))
    for f in SHELL_CONTENT_FLAGS:
        if f in flag_values and flag_values[f] not in (None, ""):
            h.update(b"|")
            h.update(f.encode("utf-8"))
            h.update(b"=")
            h.update(str(flag_values[f]).encode("utf-8"))
    return h.hexdigest()[:10]


def _shell_summarize(script_name: str, flag_values: dict) -> str:
    label = {
        "--md": "文档", "--title": "标题前缀", "--title-key": "标题键",
        "--space": "空间", "--root": "根目录", "--epic": "Epic",
        "--kind": "类型", "--parent": "父页", "--initiative": "Initiative",
    }
    parts = [f"脚本：{script_name}（REST 上传 Confluence）"]
    for f in ("--kind", "--space", "--epic", "--title", "--title-key", "--md"):
        if f in flag_values and flag_values[f]:
            v = str(flag_values[f]).replace("\n", " ").strip()
            if len(v) > 120:
                v = v[:119] + "…"
            parts.append(f"{label.get(f, f)}：{v}")
    return "  |  ".join(parts)


def _summarize(tool_name: str, tool_input: dict) -> str:
    def clip(v, n=160):
        s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
        s = s.replace("\n", " ").strip()
        return s if len(s) <= n else s[: n - 1] + "…"

    parts = [f"工具：{tool_name}"]
    label = {
        "title": "标题", "summary": "摘要", "body": "正文",
        "description": "描述", "commentBody": "评论", "comment": "评论",
        "spaceId": "空间", "projectKey": "项目", "issueIdOrKey": "工单",
        "issueKey": "工单", "transition": "流转到", "status": "状态",
        "timeSpent": "工时", "type": "链接类型",
    }
    for f in ("issueIdOrKey", "issueKey", "projectKey", "spaceId", "title", "summary",
              "transition", "status", "timeSpent", "type", "body", "description",
              "commentBody", "comment"):
        if f in tool_input and tool_input[f] not in (None, "", [], {}):
            parts.append(f"{label.get(f, f)}：{clip(tool_input[f])}")
    return "  |  ".join(parts)


def _approve_cmd_hint(code: str) -> str:
    """给用户看的一行批准命令（尽量用与本进程一致的解释器路径）。"""
    py = sys.executable or "python3"
    script = str(Path(__file__).resolve())
    # 路径含空格时给出带引号形式，便于直接复制
    return f'"{py}" "{script}" --approve {code}'


def _emit(decision: dict) -> None:
    sys.stdout.write(json.dumps(decision, ensure_ascii=False))
    sys.stdout.flush()


def _allow() -> dict:
    return {"permission": "allow"}


def _deny(user_message: str, agent_message: str) -> dict:
    return {"permission": "deny", "user_message": user_message, "agent_message": agent_message}


def _consume_approval(code: str) -> bool:
    """检查并消费一次放行凭证：命中且未过期返回 True，并删除凭证（用后即焚）。

    两种凭证：
      1) approved/<code>          —— 针对具体内容指纹的精确批准
      2) APPROVE_NEXT             —— 无差别批准"下一个"写操作（不校验指纹）
    """
    # 1) 精确指纹批准
    exact = APPROVED_DIR / code
    if exact.is_file():
        try:
            age = _now() - exact.stat().st_mtime
        except OSError:
            age = 0
        if age <= APPROVAL_TTL_SEC:
            try:
                exact.unlink()
            except OSError:
                pass
            return True
        # 过期则清掉
        try:
            exact.unlink()
        except OSError:
            pass

    # 2) 无差别"下一个"批准
    if APPROVE_NEXT_FLAG.is_file():
        try:
            age = _now() - APPROVE_NEXT_FLAG.stat().st_mtime
        except OSError:
            age = 0
        if age <= APPROVAL_TTL_SEC:
            try:
                APPROVE_NEXT_FLAG.unlink()
            except OSError:
                pass
            return True
        try:
            APPROVE_NEXT_FLAG.unlink()
        except OSError:
            pass
    return False


def _write_pending(code: str, server_name: str, tool_name: str, summary: str) -> None:
    try:
        PENDING_DIR.mkdir(parents=True, exist_ok=True)
        rec = {
            "code": code,
            "server": server_name,
            "tool": tool_name,
            "summary": summary,
            "ts": _now(),
        }
        (PENDING_DIR / f"{code}.json").write_text(
            json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError:
        pass  # pending 只是给用户看的辅助记录，写失败不影响拦截决策


# ---------------- CLI：用户手动批准入口（模型碰不到）----------------

def _cli_approve(code: str) -> int:
    APPROVED_DIR.mkdir(parents=True, exist_ok=True)
    (APPROVED_DIR / code).write_text(str(_now()), encoding="utf-8")
    print(f"[guard] 已批准操作码 {code}，将放行下一次相同内容的重试（有效期 {APPROVAL_TTL_SEC//60} 分钟，一次性）。")
    return 0


def _cli_approve_next() -> int:
    GUARD_HOME.mkdir(parents=True, exist_ok=True)
    APPROVE_NEXT_FLAG.write_text(str(_now()), encoding="utf-8")
    print(f"[guard] 已批准『下一个』Atlassian 写操作（不校验内容，有效期 {APPROVAL_TTL_SEC//60} 分钟，一次性）。")
    return 0


def _cli_list_pending() -> int:
    if not PENDING_DIR.is_dir():
        print("[guard] 暂无待批准的写操作。")
        return 0
    files = sorted(PENDING_DIR.glob("*.json"))
    if not files:
        print("[guard] 暂无待批准的写操作。")
        return 0
    print(f"[guard] 待批准的写操作（{len(files)} 条）：")
    for f in files:
        try:
            rec = json.loads(f.read_text(encoding="utf-8"))
            print(f"  - {rec.get('code')}  {rec.get('tool')}  {rec.get('summary','')}")
        except Exception:
            print(f"  - {f.stem}  (记录解析失败)")
    return 0


def _run_cli(argv: list[str]) -> int:
    if not argv:
        return 1
    cmd = argv[0]
    if cmd == "--approve" and len(argv) >= 2:
        return _cli_approve(argv[1].strip())
    if cmd == "--approve-next":
        return _cli_approve_next()
    if cmd in ("--list", "--pending"):
        return _cli_list_pending()
    if cmd in ("-h", "--help"):
        print(__doc__)
        return 0
    print(f"[guard] 未知参数：{argv}\n用法：--approve <操作码> | --approve-next | --list", file=sys.stderr)
    return 2


# ---------------- 确认闸门（MCP / Shell 共用）----------------

def _gate(code: str, summary: str, kind: str, detail_for_agent: str) -> dict:
    """统一的确认闸门：已批准则 allow（用后即焚），否则 deny 并给出批准指引。

    kind：给用户/agent 看的操作类别描述，如 "Atlassian 写操作" / "Confluence REST 上传"。
    detail_for_agent：拼进 agent_message 的、本次调用的定位信息。
    """
    if _consume_approval(code):
        return _allow()

    _write_pending(code, kind, kind, summary)
    approve_cmd = _approve_cmd_hint(code)
    user_message = (
        f"🛑 AI SDLC 安全闸门：AI 试图执行【{kind}】，已被拦截，等待你确认。\n"
        f"  操作码：{code}\n"
        f"  内容：{summary}\n"
        "  ── 如果确认无误，把下面这行复制到终端执行后，让 AI 重试即可放行：\n"
        f"    {approve_cmd}\n"
        "  （或执行 --approve-next 批准下一个写操作而不校验内容；批准一次性、默认 30 分钟内有效。）"
    )
    agent_message = (
        f"你即将执行的【{kind}】（{detail_for_agent}）已被 AI SDLC 安全闸门拦截。"
        "这是团队强制的人工确认闸门，任何模型都必须遵守。\n"
        "你现在必须：\n"
        "1) 停止该写入动作，把【将要提交的完整内容】（标题、正文/摘要、目标空间或项目、"
        "工单号、状态流转、上传的文档路径等）清楚地念给用户，请用户确认；\n"
        "2) 等用户明确批准后，【原样重试同一个调用/命令】——参数不要改动；\n"
        "3) 严禁伪造、猜测或自行构造任何确认信息，也不要试图绕过本闸门（例如改用别的工具、"
        "拆分内容、或去掉 --dry-run 以外的方式规避）。放行动作只能由用户在终端手动执行，"
        "你无法自行完成。\n"
        f"（本次操作码 {code}，用户批准后闸门会自动放行你的重试。）"
    )
    return _deny(user_message, agent_message)


# ---------------- hook 主流程 ----------------

def _run_hook() -> int:
    # fail-safe：任何解析异常都 deny，避免"解析失败 = 放行"的安全漏洞。
    try:
        payload = _read_stdin_json()
    except Exception as e:
        _emit(_deny(
            user_message=f"⚠️ AI SDLC 安全闸门无法解析 hook 输入，已拦截该调用（原因：{e}）。",
            agent_message=("安全闸门无法解析本次调用输入，已按 fail-safe 拦截。"
                           "请重试；若持续失败，请提示用户检查 guard_atlassian.py hook。"),
        ))
        return 0

    # ---- 分支 A：Shell 事件（beforeShellExecution）----
    # 特征：payload 里有 command 且没有 tool_name（MCP 事件也有 command 字段表示启动命令，
    # 但 MCP 事件必带 tool_name，据此区分）。
    command = str(payload.get("command", "") or "")
    tool_name = str(payload.get("tool_name", "") or "")
    if command and not tool_name:
        return _run_shell_gate(command)

    # ---- 分支 B：MCP 事件（beforeMCPExecution）----
    return _run_mcp_gate(payload)


def _run_shell_gate(command: str) -> int:
    script = _shell_hits_write_script(command)
    if not script:
        # 与本闸门无关的普通 shell 命令 → 放行
        _emit(_allow())
        return 0

    tokens = _tokenize_command(command)
    if _shell_is_dry_run(tokens):
        # dry-run / check-env 只预检、不写库 → 放行不打扰
        _emit(_allow())
        return 0

    flag_values = _parse_flag_values(tokens)
    code = _shell_fingerprint(script, flag_values)
    summary = _shell_summarize(script, flag_values)
    _emit(_gate(
        code, summary,
        kind="Confluence REST 上传",
        detail_for_agent=f"script={script}",
    ))
    return 0


def _run_mcp_gate(payload: dict) -> int:
    server_name = str(payload.get("mcp_server_name", "") or "")
    tool_name = str(payload.get("tool_name", "") or "")
    command = str(payload.get("command", "") or "")
    tool_input = _parse_tool_input(payload.get("tool_input"))

    # 1) 非 Atlassian server → 与本闸门无关，放行
    if not _is_atlassian(server_name, command):
        _emit(_allow())
        return 0

    # 2) Atlassian 的只读操作 → 放行，不打扰
    if not _is_write_tool(tool_name):
        _emit(_allow())
        return 0

    # 3) Atlassian 写操作 → 走确认闸门
    code = _fingerprint(server_name, tool_name, tool_input)
    summary = _summarize(tool_name, tool_input)
    _emit(_gate(
        code, summary,
        kind="Atlassian 写操作",
        detail_for_agent=f"server={server_name} tool={tool_name}",
    ))
    return 0


def main() -> int:
    argv = sys.argv[1:]
    if argv:
        return _run_cli(argv)
    return _run_hook()


if __name__ == "__main__":
    sys.exit(main())

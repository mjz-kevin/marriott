#!/usr/bin/env python3
"""profile-select:AI SDLC 团队 profile 的选择与本机记忆。

profile 文件放在仓库内 `.cursor/profiles/*.yaml`,便于共享与版本管理。
而"当前用哪个 profile"的选择是每台机器 + 每个仓库各自的,保存在用户本机
(不在仓库内),因此只需询问一次;之后各 Agent / Skill 都从这里读取,
除非用户明确要求切换。

本机选择文件:
  $PROFILE_SELECT_HOME/selection.json                          (若设置了 PROFILE_SELECT_HOME)
  否则  %APPDATA%\\ai-sdlc-profile-select\\selection.json        (Windows 默认)
  否则  ~/.config/ai-sdlc-profile-select/selection.json         (macOS / Linux 默认)

selection.json 按仓库根路径分别记忆:
  {"selections": {"/abs/repo/root": "app-prod"}}

用法:
  python profile.py list                 # 列出仓库内可用的 profile 及其关键字段
  python profile.py show                 # 显示当前仓库本机已记住的 profile
  python profile.py use <名称>            # 记住选择(替换),名称为文件名去掉 .yaml
  python profile.py resolve              # 打印当前 profile 的绝对路径(供其他 Skill 读取)
  python profile.py clear                # 清除当前仓库的记忆
  python profile.py path                 # 打印选择文件路径

退出码:
  0 成功;2 未记住选择 / profile 不存在(需要询问用户);3 用法或环境错误。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import platform_paths  # noqa: E402


def find_profiles_dir():
    """从脚本位置向上查找包含 .cursor/profiles 的仓库根。

    返回 (repo_root, profiles_dir);找不到返回 (None, None)。
    优先用脚本自身所在路径(skill 在 <root>/.cursor/skills/profile-select/scripts),
    再回退到当前工作目录向上查找。
    """
    candidates = [os.path.abspath(os.path.dirname(__file__)), os.path.abspath(os.getcwd())]
    for start in candidates:
        cur = start
        while True:
            profiles = os.path.join(cur, ".cursor", "profiles")
            if os.path.isdir(profiles):
                return cur, profiles
            parent = os.path.dirname(cur)
            if parent == cur:
                break
            cur = parent
    return None, None


def available_profiles(profiles_dir):
    if not profiles_dir or not os.path.isdir(profiles_dir):
        return []
    names = []
    for f in os.listdir(profiles_dir):
        if (f.endswith(".yaml") or f.endswith(".yml")) and not f.startswith("."):
            names.append(os.path.splitext(f)[0])
    return sorted(names)


def profile_path(profiles_dir, name):
    for ext in (".yaml", ".yml"):
        p = os.path.join(profiles_dir, name + ext)
        if os.path.isfile(p):
            return p
    return None


def summarize(path):
    """轻量提取用于辨认的关键字段,不依赖第三方库。

    返回 dict:team / display_name / confluence_space / jira_project_key。
    """
    info = {"team": "", "display_name": "", "confluence_space": "", "jira_project_key": ""}
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        return info

    def indent(s):
        return len(s) - len(s.lstrip(" "))

    section = []  # 当前缩进层级下的键路径(仅按缩进跟踪 mcp/confluence/jira)
    for raw in lines:
        line = raw.rstrip("\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        stripped = line.strip()
        ind = indent(line)
        # 维护简单的段落栈
        while section and ind <= section[-1][1]:
            section.pop()
        if ":" not in stripped:
            continue
        key = stripped.split(":", 1)[0].strip()
        val = stripped.split(":", 1)[1].strip()
        # 去掉行内注释与引号
        if val:
            val = val.split(" #", 1)[0].strip().strip('"').strip("'")
        path_keys = [k for k, _ in section]
        if ind == 0 and key == "team":
            info["team"] = val
        elif ind == 0 and key == "display_name":
            info["display_name"] = val
        elif path_keys == ["mcp", "confluence"] and key == "space":
            info["confluence_space"] = val
        elif path_keys == ["mcp", "jira"] and key == "project_key":
            info["jira_project_key"] = val
        # 无值 → 视为进入子段落
        if val == "":
            section.append((key, ind))
    return info


def selection_dir():
    return platform_paths.default_config_dir()


def selection_path():
    return os.path.join(selection_dir(), "selection.json")


def _load_all():
    p = selection_path()
    if not os.path.isfile(p):
        return {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        sel = data.get("selections", {})
        return sel if isinstance(sel, dict) else {}
    except Exception:
        return {}


def get_selected(repo_root):
    return _load_all().get(repo_root or "", "")


def set_selected(repo_root, name):
    d = selection_dir()
    os.makedirs(d, exist_ok=True)
    all_sel = _load_all()
    all_sel[repo_root or ""] = name
    with open(selection_path(), "w", encoding="utf-8") as f:
        json.dump({"selections": all_sel}, f, ensure_ascii=False, indent=2)


def clear_selected(repo_root):
    all_sel = _load_all()
    if (repo_root or "") in all_sel:
        del all_sel[repo_root or ""]
        with open(selection_path(), "w", encoding="utf-8") as f:
            json.dump({"selections": all_sel}, f, ensure_ascii=False, indent=2)
        return True
    return False


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(3)
    cmd = sys.argv[1]
    args = sys.argv[2:]

    repo_root, profiles_dir = find_profiles_dir()

    if cmd == "path":
        print(selection_path())
        sys.exit(0)

    if cmd == "list":
        if not profiles_dir:
            print("[profile-select] 未找到 .cursor/profiles 目录")
            sys.exit(3)
        names = available_profiles(profiles_dir)
        if not names:
            print("[profile-select] .cursor/profiles 下没有 profile 文件")
            sys.exit(2)
        print("可用 profile:")
        for n in names:
            s = summarize(profile_path(profiles_dir, n))
            desc = " / ".join(
                x for x in [
                    f"team={s['team']}" if s["team"] else "",
                    s["display_name"],
                    f"space={s['confluence_space']}" if s["confluence_space"] else "",
                    f"jira={s['jira_project_key']}" if s["jira_project_key"] else "",
                ] if x
            )
            print(f"  - {n}    {desc}")
        sys.exit(0)

    if cmd == "show":
        sel = get_selected(repo_root)
        print(f"平台:{platform_paths.platform_label()}")
        print(f"仓库根:{repo_root or '(未找到)'}")
        print(f"选择文件:{selection_path()}")
        print(f"当前记住的 profile:{sel or '(尚未选择)'}")
        if sel and profiles_dir and not profile_path(profiles_dir, sel):
            print(f"警告:记住的 profile '{sel}' 在当前仓库不存在,请重新选择。")
            sys.exit(2)
        sys.exit(0 if sel else 2)

    if cmd == "use":
        if len(args) != 1:
            print("用法:profile.py use <名称>")
            sys.exit(3)
        if not profiles_dir:
            print("[profile-select] 未找到 .cursor/profiles 目录")
            sys.exit(3)
        name = os.path.splitext(args[0])[0]
        if not profile_path(profiles_dir, name):
            print(f"[profile-select] profile '{name}' 不存在。可用:{'、'.join(available_profiles(profiles_dir)) or '(无)'}")
            sys.exit(2)
        set_selected(repo_root, name)
        print(f"[profile-select] 已记住 profile:{name}(仓库 {repo_root})")
        sys.exit(0)

    if cmd == "resolve":
        sel = get_selected(repo_root)
        if not sel:
            print("[profile-select] 尚未记住 profile,请先询问用户并 use。", file=sys.stderr)
            sys.exit(2)
        if not profiles_dir:
            print("[profile-select] 未找到 .cursor/profiles 目录", file=sys.stderr)
            sys.exit(3)
        p = profile_path(profiles_dir, sel)
        if not p:
            print(f"[profile-select] 记住的 profile '{sel}' 已不存在,请重新选择。", file=sys.stderr)
            sys.exit(2)
        print(p)
        sys.exit(0)

    if cmd == "clear":
        ok = clear_selected(repo_root)
        print("[profile-select] 已清除记忆。" if ok else "[profile-select] 当前仓库没有记忆。")
        sys.exit(0)

    print(__doc__)
    sys.exit(3)


if __name__ == "__main__":
    main()

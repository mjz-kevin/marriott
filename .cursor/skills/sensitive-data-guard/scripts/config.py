#!/usr/bin/env python3
"""sensitive-data-guard 白名单选择管理器。

白名单本身放在 skill 内(whitelists/*.json),便于共享和版本管理。而"使用哪些
白名单"的选择是每台机器各自的,保存在用户本机(不在 skill 内),因此只需询问一次。

本机选择文件:
  $SENSITIVE_DATA_GUARD_HOME/selection.json                    (若设置了 SENSITIVE_DATA_GUARD_HOME)
  否则  %APPDATA%\\sensitive-data-guard\\selection.json         (Windows 默认)
  否则  ~/.config/sensitive-data-guard/selection.json           (macOS / Linux 默认)

selection.json 格式:
  {"selected": ["default", "team-marriott"]}

用法:
  python3 config.py list                 # 列出 skill 内可用的白名单
  python3 config.py show                 # 显示当前本机选择
  python3 config.py use 名称 [名称 ...]   # 设置选择(替换)
  python3 config.py add 名称              # 向选择中追加一份
  python3 config.py create 名称           # 在 skill 内生成新的白名单
  python3 config.py path                 # 打印选择文件路径
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import platform_paths  # noqa: E402

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WHITELIST_DIR = os.path.join(SKILL_DIR, "whitelists")


def selection_dir():
    return platform_paths.default_config_dir()


def selection_path():
    return os.path.join(selection_dir(), "selection.json")


def available_whitelists():
    if not os.path.isdir(WHITELIST_DIR):
        return []
    return sorted(
        f[:-5] for f in os.listdir(WHITELIST_DIR)
        if f.endswith(".json") and not f.startswith(".")
    )


def get_selected_whitelists():
    """返回已选择的白名单名称列表;若尚未选择则返回 []。"""
    path = selection_path()
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        sel = data.get("selected", [])
        return [s for s in sel if isinstance(s, str)]
    except Exception:
        return []


def has_selection():
    return os.path.isfile(selection_path()) and bool(get_selected_whitelists())


def set_selection(names):
    d = selection_dir()
    os.makedirs(d, exist_ok=True)
    with open(selection_path(), "w", encoding="utf-8") as f:
        json.dump({"selected": list(dict.fromkeys(names))}, f, ensure_ascii=False, indent=2)


def create_whitelist(name):
    os.makedirs(WHITELIST_DIR, exist_ok=True)
    path = os.path.join(WHITELIST_DIR, name + ".json")
    if os.path.isfile(path):
        print(f"[sensitive-data-guard] 白名单 '{name}' 已存在(路径 {path})")
        return path
    template = {
        "name": name,
        "description": "即使命中检测器也可安全写入的值。",
        "literals": [],
        "patterns": [],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(template, f, ensure_ascii=False, indent=2)
    print(f"[sensitive-data-guard] 已创建白名单 '{name}'(路径 {path})")
    return path


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    cmd = sys.argv[1]
    args = sys.argv[2:]

    if cmd == "list":
        wl = available_whitelists()
        print("skill 内可用的白名单:")
        for w in wl:
            print(f"  - {w}")
        if not wl:
            print("  (无)")
    elif cmd == "show":
        sel = get_selected_whitelists()
        print(f"平台:{platform_paths.platform_label()}")
        print(f"配置目录说明:{platform_paths.default_config_dir_hint()}")
        print(f"选择文件:{selection_path()}")
        print(f"已选择:{'、'.join(sel) if sel else '(尚未选择)'}")
    elif cmd == "use":
        if not args:
            print("用法:config.py use 名称 [名称 ...]")
            sys.exit(1)
        set_selection(args)
        print(f"[sensitive-data-guard] 已将选择设置为:{'、'.join(args)}")
    elif cmd == "add":
        if len(args) != 1:
            print("用法:config.py add 名称")
            sys.exit(1)
        sel = get_selected_whitelists()
        sel.append(args[0])
        set_selection(sel)
        print(f"[sensitive-data-guard] 当前选择:{'、'.join(get_selected_whitelists())}")
    elif cmd == "create":
        if len(args) != 1:
            print("用法:config.py create 名称")
            sys.exit(1)
        create_whitelist(args[0])
    elif cmd == "path":
        print(selection_path())
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()

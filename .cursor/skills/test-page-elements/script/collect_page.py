"""附着当前前台 iOS App，dump 当前页面 page source（test-page-elements 采集用固定脚本）。

用途：真机把 App 停在要采集的页面后，运行本脚本 → 打印当前页面的 XCUITest page source，
供 test-page-elements skill 分析、整理成 Page Object 元组 locator + Confluence 元素文档。

特性：
- **不重启 / 不切换 App**：noReset + 不带 bundleId，直接附着当前前台，采集的就是眼前那一页。
- **不落地 png / xml**：默认打印到 stdout；仅当显式传 --out / 设 DUMP_OUT 时才写文件（临时用，用完自行删）。
- 连接配置优先读项目 config/env/.env.ios.<ENV>（与 conftest 一致），回退到 ios_test_config / 环境变量默认值。

用法（在仓库根目录，激活 .venv 后）：
    python .cursor/skills/test-page-elements/script/collect_page.py
    python .cursor/skills/test-page-elements/script/collect_page.py --out /tmp/page_dump.txt
可覆盖的环境变量：APPIUM_SERVER_URL / IOS_UDID(或 DEVICE_ID) / WDA_BUNDLE_ID / XCODE_ORG_ID / DEVICE_NAME / ENV
"""
import argparse
import os
import sys
from pathlib import Path


def _load_project_env() -> None:
    """尽量复用项目 config/env/.env.ios.<ENV>，与 tests/mobile/ios/conftest.py 对齐。

    找不到 .env 或 dotenv 未装都不致命——继续用现有环境变量 / 下面的默认值。
    """
    # 仓库根：本文件在 <root>/.cursor/skills/test-page-elements/script/ 下，向上 5 层
    root = Path(__file__).resolve().parents[4]
    env_name = os.getenv("ENV", "lle").lower()
    env_file = root / "config" / "env" / f".env.ios.{env_name}"
    if not env_file.exists():
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(dotenv_path=env_file, override=False)
    except Exception:
        # 简易兜底：手动解析 KEY=VALUE（不覆盖已存在的环境变量）
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())


def build_options():
    from appium.options.ios import XCUITestOptions

    opts = XCUITestOptions()
    opts.platform_name = "iOS"
    opts.automation_name = "XCUITest"
    opts.device_name = os.getenv("DEVICE_NAME", "iPhone")
    # UDID：优先 IOS_UDID，其次 conftest 使用的 DEVICE_ID
    udid = os.getenv("IOS_UDID") or os.getenv("DEVICE_ID")
    if udid:
        opts.udid = udid
    opts.no_reset = True  # 关键：不重置、不切换当前前台 App
    opts.set_capability("newCommandTimeout", 120)
    if xcode_org := os.getenv("XCODE_ORG_ID"):
        opts.set_capability("xcodeOrgId", xcode_org)
    if wda_bundle := os.getenv("WDA_BUNDLE_ID"):
        opts.set_capability("updatedWDABundleId", wda_bundle)
    # 复用已编译的 WDA 加速附着；首次编译请设 USE_PREBUILT_WDA=false
    opts.set_capability(
        "usePrebuiltWDA",
        os.getenv("USE_PREBUILT_WDA", "true").lower() == "true",
    )
    # 注意：不设 bundleId / app —— 附着当前前台，不切换页面
    return opts


def main() -> int:
    parser = argparse.ArgumentParser(description="Dump current foreground iOS page source.")
    parser.add_argument(
        "--out",
        default=os.getenv("DUMP_OUT"),
        help="可选：把 page source 写到该文件（默认只打印到 stdout，不落地文件）。",
    )
    args = parser.parse_args()

    _load_project_env()

    try:
        from appium import webdriver
    except ImportError:
        print(
            "ERROR: 未找到 Appium-Python-Client，请先激活项目 .venv 并 pip install -r requirements.txt",
            file=sys.stderr,
        )
        return 2

    appium_url = os.getenv("APPIUM_SERVER_URL", "http://127.0.0.1:4723")
    opts = build_options()

    try:
        driver = webdriver.Remote(appium_url, options=opts)
    except Exception as exc:  # noqa: BLE001
        print(
            f"ERROR: 连接 Appium 失败（{appium_url}）：{exc}\n"
            "请确认：① Appium Server 已启动；② iOS 真机已连接解锁；"
            "③ RemoteXPC 隧道已起（iOS 17+ 真机需要）；④ .env.ios.lle 里 DEVICE_ID/WDA 等已配置。",
            file=sys.stderr,
        )
        return 1

    try:
        src = driver.page_source
        size = driver.get_window_size()
    finally:
        driver.quit()

    body = f"WINDOW_SIZE: {size}\nPAGE_SOURCE_START\n{src}\nPAGE_SOURCE_END\n"
    if args.out:
        Path(args.out).write_text(body, encoding="utf-8")
        print(f"WINDOW_SIZE: {size}")
        print(f"page source written to {args.out} ({len(src)} chars)")
    else:
        sys.stdout.write(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

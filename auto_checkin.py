"""
ViewTurbo 自动签到脚本（多账号版）
支持多个账号顺序签到，通过环境变量配置

环境变量：
    VIEWTURBO_ACCOUNTS - 账号列表，格式: "email1:pass1,email2:pass2"

用法:
    python auto_checkin.py start   # 后台启动
    python auto_checkin.py stop    # 停止
    python auto_checkin.py status  # 查看状态
    python auto_checkin.py run     # 前台运行（多账号顺序签到）
"""

import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
import logging
from datetime import datetime
from pathlib import Path

import requests

# ============ 配置 ============
API_BASE = "https://api.viewturbo.com"
# =============================

# 日志配置
log_file = Path(__file__).parent / "checkin.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

# PID 文件
PID_FILE = Path(__file__).parent / "auto_checkin.pid"


def write_pid():
    PID_FILE.write_text(str(os.getpid()))


def read_pid():
    if PID_FILE.exists():
        return int(PID_FILE.read_text().strip())
    return None


def remove_pid():
    if PID_FILE.exists():
        PID_FILE.unlink()


def is_running():
    pid = read_pid()
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        remove_pid()
        return False


def md5(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()


def load_accounts():
    """从环境变量 VIEWTURBO_ACCOUNTS 加载账号列表"""
    acc_str = os.getenv("VIEWTURBO_ACCOUNTS")
    if not acc_str:
        raise Exception("未设置环境变量 VIEWTURBO_ACCOUNTS，格式: email1:pass1,email2:pass2")

    accounts = []
    for pair in acc_str.split(','):
        pair = pair.strip()
        if not pair:
            continue
        if ':' not in pair:
            raise ValueError(f"账号格式错误，应为 email:password，却得到: {pair}")
        email, pwd = pair.split(':', 1)
        accounts.append({'email': email, 'password': pwd})
    if not accounts:
        raise Exception("VIEWTURBO_ACCOUNTS 中没有有效的账号")
    return accounts


def login(email: str, password: str) -> str:
    """登录获取 token"""
    url = f"{API_BASE}/appuser/reglogin?platform=web&cur_version=0.0.0&lang=hk"
    payload = {"email": email, "password": md5(password)}
    resp = requests.post(url, json=payload, timeout=15)
    data = resp.json()
    if data.get("code") == 0:
        token = data["data"]["token"]
        log.info("登录成功, token: %s...%s", token[:6], token[-4:])
        return token
    else:
        raise Exception(f"登录失败: {data.get('msg')}")


def checkin(token: str) -> dict:
    """执行签到"""
    url = (
        f"{API_BASE}/appuser/checkin"
        f"?platform=web&cur_version=0.0.0&token={token}"
        f"&deviceinfo=&lang=hk&code=Others"
    )
    resp = requests.post(url, timeout=15)
    return resp.json()


def _shutdown(signum, frame):
    log.info("收到停止信号，正在退出...")
    remove_pid()
    sys.exit(0)


def run():
    """前台运行签到循环（多账号顺序签到）"""
    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)
    write_pid()

    log.info("=" * 50)
    log.info("ViewTurbo 自动签到启动 (多账号顺序签到)")
    log.info("=" * 50)

    try:
        accounts = load_accounts()
    except Exception as e:
        log.error("加载账号失败: %s", e)
        sys.exit(1)

    log.info("共加载 %d 个账号", len(accounts))

    MAX_RETRIES = 3
    RETRY_DELAY = 10

    for idx, acc in enumerate(accounts, start=1):
        email = acc['email']
        password = acc['password']
        log.info(">>> 正在处理第 %d/%d 个账号: %s", idx, len(accounts), email)

        success = False
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                log.info("  第 %d/%d 次尝试", attempt, MAX_RETRIES)
                token = login(email, password)
                result = checkin(token)
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                if result.get("code") == 0:
                    d = result.get("data", {})
                    log.info(
                        "  [%s] 签到成功! 连续 %d 天, 奖励: %s",
                        now,
                        d.get("consecutive", 0),
                        d.get("reward_display", "unknown")
                    )
                    success = True
                    break

                elif result.get("code") == 7:
                    log.warning("  Token 过期，重新登录...")
                    token = login(email, password)
                    result = checkin(token)
                    if result.get("code") == 0:
                        d = result.get("data", {})
                        log.info(
                            "  [%s] 签到成功! 连续 %d 天, 奖励: %s",
                            now,
                            d.get("consecutive", 0),
                            d.get("reward_display", "unknown")
                        )
                        success = True
                        break

                elif "已签到" in result.get("msg", ""):
                    log.info("  今天已签到，跳过")
                    success = True
                    break

                else:
                    log.warning("  签到返回异常: %s", json.dumps(result, ensure_ascii=False))

            except requests.exceptions.RequestException as e:
                log.error("  网络错误: %s", e)
            except Exception as e:
                log.error("  发生错误: %s", e)

            if attempt < MAX_RETRIES:
                log.info("  等待 %d 秒后重试...", RETRY_DELAY)
                time.sleep(RETRY_DELAY)

        if not success:
            log.error("账号 %s 签到失败（已达最大重试次数）", email)

        # 账号间稍作延迟，避免请求过快
        if idx < len(accounts):
            time.sleep(2)

    log.info("所有账号处理完成，退出")
    sys.exit(0)


def do_start():
    """后台启动服务"""
    # 检查账号配置是否有效
    try:
        load_accounts()
    except Exception as e:
        print(f"错误: {e}")
        sys.exit(1)

    if is_running():
        pid = read_pid()
        print(f"服务已在运行中 (PID: {pid})")
        return

    pythonw = sys.executable.replace("python", "pythonw")
    if not os.path.exists(pythonw):
        pythonw = sys.executable

    proc = subprocess.Popen(
        [pythonw, __file__, "run"],
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        cwd=str(Path(__file__).parent),
    )
    print(f"服务已启动 (PID: {proc.pid})")


def do_stop():
    pid = read_pid()
    if pid is None:
        print("服务未运行")
        return
    try:
        os.kill(pid, signal.SIGTERM)
        print(f"服务已停止 (PID: {pid})")
    except ProcessLookupError:
        print("进程已不存在")
    finally:
        remove_pid()


def do_status():
    if is_running():
        print(f"服务运行中 (PID: {read_pid()})")
    else:
        print("服务未运行")


def main():
    parser = argparse.ArgumentParser(description="ViewTurbo 自动签到（多账号版）")
    parser.add_argument(
        "command",
        choices=["start", "stop", "status", "run"],
        nargs="?",
        default="status",
        help="操作命令 (默认: status)",
    )
    args = parser.parse_args()

    commands = {
        "start": do_start,
        "stop": do_stop,
        "status": do_status,
        "run": run,
    }
    commands[args.command]()


if __name__ == "__main__":
    main()

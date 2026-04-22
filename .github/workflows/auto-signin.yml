"""
ViewTurbo 自动签到脚本
每隔 20 秒自动签到一次，自动登录刷新 token

用法:
    python auto_checkin.py start   # 后台启动
    python auto_checkin.py stop    # 停止
    python auto_checkin.py status  # 查看状态
    python auto_checkin.py run     # 前台运行
"""

import argparse
import hashlib
import json
import os
import random
import signal
import subprocess
import sys
import time
import logging
from datetime import datetime
from pathlib import Path

import requests

# ============ 配置 ============
EMAIL = "fxg9527@gmail.com"
PASSWORD = "good7453390dong"
# RANDOM_INTERVALS = [15, 26, 28, 32, 40, 47, 55]  # 随机签到间隔（秒）
RANDOM_INTERVALS = [15, 26]  # 随机签到间隔（秒）
API_BASE = "https://api.viewturbo.com"
# ==============================

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


def login() -> str:
    """登录获取 token"""
    url = f"{API_BASE}/appuser/reglogin?platform=web&cur_version=0.0.0&lang=hk"
    payload = {"email": EMAIL, "password": md5(PASSWORD)}
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
    """前台运行签到循环"""
    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)
    write_pid()

    log.info("=" * 50)
    log.info("ViewTurbo 自动签到启动 (随机间隔 %s 秒)", RANDOM_INTERVALS)
    log.info("=" * 50)

    token = None

    while True:
        try:
            # 确保 token 有效
            if not token:
                token = login()

            # 执行签到
            result = checkin(token)
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            if result.get("code") == 0:
                d = result.get("data", {})
                log.info(
                    "[%s] 签到成功! 连续 %d 天, 奖励: %s",
                    now,
                    d.get("consecutive", 0),
                    d.get("reward_display", "unknown"),
                )
            elif result.get("code") == 7:
                # token 过期，重新登录
                log.warning("[%s] Token 过期，重新登录...", now)
                token = login()
                # 用新 token 重试签到
                result = checkin(token)
                if result.get("code") == 0:
                    d = result.get("data", {})
                    log.info(
                        "[%s] 签到成功! 连续 %d 天, 奖励: %s",
                        now,
                        d.get("consecutive", 0),
                        d.get("reward_display", "unknown"),
                    )
                else:
                    log.warning("[%s] 重试签到返回: %s", now, result.get("msg"))
            else:
                log.warning("[%s] 签到返回异常: %s", now, json.dumps(result, ensure_ascii=False))

        except requests.exceptions.RequestException as e:
            log.error("网络错误: %s", e)
        except Exception as e:
            log.error("发生错误: %s", e)

        # 随机等待下次签到
        interval = random.choice(RANDOM_INTERVALS)
        log.info("下次签到将在 %d 秒后", interval)
        time.sleep(interval)


def do_start():
    """后台启动服务"""
    if is_running():
        pid = read_pid()
        print(f"服务已在运行中 (PID: {pid})")
        return
    # Windows: 用 pythonw 后台运行
    pythonw = sys.executable.replace("python", "pythonw")
    if not os.path.exists(pythonw):
        pythonw = sys.executable
    proc = subprocess.Popen(
        [pythonw, __file__, "run"],
        creationflags=subprocess.CREATE_NO_WINDOW,
        cwd=str(Path(__file__).parent),
    )
    print(f"服务已启动 (PID: {proc.pid})")


def do_stop():
    """停止服务"""
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
    """查看服务状态"""
    if is_running():
        print(f"服务运行中 (PID: {read_pid()})")
    else:
        print("服务未运行")


def main():
    parser = argparse.ArgumentParser(description="ViewTurbo 自动签到")
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

#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""
cron: 0 21 * * *
new Env('ikuuu签到')
"""

import os
import sys
import requests
import json
import re
import random
import time
from urllib.parse import unquote
from datetime import datetime

# ---------------- 统一通知模块加载 ----------------
hadsend = False
send = None
try:
    from notify import send

    hadsend = True
    print("✅ 已加载notify.py通知模块")
except ImportError:
    print("⚠️  未加载通知模块，跳过通知功能")


def notify_user(title, content):
    """统一通知发送"""
    if hadsend:
        try:
            send(title, content)
            print(f"✅ 通知发送完成: {title}")
        except Exception as e:
            print(f"❌ 通知发送失败: {e}")
    else:
        print(f"📢 {title}\n📄 {content}")


def get_base_dir():
    return os.path.dirname(os.path.abspath(__file__))


def load_config():
    """读取全局配置"""
    config_path = os.path.join(get_base_dir(), "config.json")
    default_config = {
        "base_url": os.getenv("IKUUU_BASE_URL", "https://ikuuu.top"),
        "interval_min": 2,
        "interval_max": 5
    }

    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                file_config = json.load(f)
                if isinstance(file_config, dict):
                    default_config.update(file_config)
            print(f"📁 已加载网站配置: {config_path}")
        except Exception as e:
            print(f"⚠️ 读取 config.json 失败: {e}")

    default_config["base_url"] = default_config["base_url"].rstrip("/")
    return default_config


def load_accounts():
    """读取 accounts.json 或环境变量 IKUUU_ACCOUNTS"""
    accounts_path = os.path.join(get_base_dir(), "accounts.json")
    raw_cookies = []

    if os.path.exists(accounts_path):
        try:
            with open(accounts_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    raw_cookies = data
                elif isinstance(data, dict) and "accounts" in data:
                    raw_cookies = data["accounts"]
            print(f"📁 已加载账号配置: {accounts_path}")
        except Exception as e:
            print(f"⚠️ 读取 accounts.json 失败: {e}")

    if not raw_cookies and os.getenv("IKUUU_ACCOUNTS"):
        try:
            data = json.loads(os.getenv("IKUUU_ACCOUNTS"))
            if isinstance(data, list):
                raw_cookies = data
            elif isinstance(data, dict) and "accounts" in data:
                raw_cookies = data["accounts"]
            print("🌐 从环境变量 IKUUU_ACCOUNTS 加载账号凭证")
        except Exception as e:
            print(f"⚠️ 解析环境变量 IKUUU_ACCOUNTS 失败: {e}")

    valid_accounts = []
    idx = 1
    for item in raw_cookies:
        cookie_str = ""
        if isinstance(item, str) and item.strip():
            cookie_str = item.strip()
        elif isinstance(item, dict) and item.get("cookie"):
            cookie_str = item["cookie"].strip()

        if cookie_str:
            valid_accounts.append({
                "index": idx,
                "cookie": cookie_str
            })
            idx += 1

    return valid_accounts


class IkuuuCookieSigner:
    def __init__(self, cookie: str, base_url: str, index: int = 1):
        self.cookie = cookie.strip()
        self.base_url = base_url
        self.user_url = f"{self.base_url}/user"
        self.check_url = f"{self.base_url}/user/checkin"
        self.index = index
        self.email = self._extract_email_from_cookie()

        self.session = requests.Session()
        self.session.trust_env = True
        self.session.headers.update({
            'origin': self.base_url,
            'referer': self.user_url,
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'cookie': self.cookie
        })

    def _extract_email_from_cookie(self):
        match = re.search(r'email=([^;]+)', self.cookie)
        if match:
            return unquote(match.group(1))
        return "未知邮箱"

    def fetch_user_traffic(self):
        """精准提取个人中心的剩余流量与今日已用流量"""
        traffic_info = {}
        try:
            resp = self.session.get(self.user_url, timeout=15)
            if resp.status_code == 200:
                html = resp.text

                # 1. 匹配“剩余流量”后面的数字+单位 (支持 48.6 GB, 48.6GB)
                patterns_rest = [
                    r'剩余流量[\s\S]*?class=["\']counter["\']>([\d\.]+)\s*([KMGT]?B)',
                    r'剩余流量[\s\S]*?(\d+(?:\.\d+)?\s*[KMGT]?B)',
                    r'class=["\']card-body["\']>[\s\S]*?(\d+(?:\.\d+)?\s*[KMGT]?B)[\s\S]*?剩余流量'
                ]
                for p in patterns_rest:
                    m = re.search(p, html, re.I)
                    if m:
                        traffic_info["rest"] = "".join(m.groups()).strip()
                        break

                # 2. 匹配“今日已用”
                patterns_today = [
                    r'今日已用[:：\s]*([\d\.]+\s*[KMGT]?B)',
                    r'今日[已]?使用[\s\S]*?(\d+(?:\.\d+)?\s*[KMGT]?B)'
                ]
                for p in patterns_today:
                    m = re.search(p, html, re.I)
                    if m:
                        traffic_info["today"] = m.group(1).strip()
                        break
        except Exception:
            pass
        return traffic_info

    def extract_reward(self, msg, result):
        patterns = [
            r'获得[了]?\s*(\d+(?:\.\d+)?\s*[KMGT]?B)',
            r'奖励[了]?\s*(\d+(?:\.\d+)?\s*[KMGT]?B)',
            r'增加[了]?\s*(\d+(?:\.\d+)?\s*[KMGT]?B)',
            r'(\d+(?:\.\d+)?\s*[KMGT]?B)',
        ]
        for pattern in patterns:
            match = re.search(pattern, msg, re.I)
            if match:
                return match.group(1).strip()
        return None

    def execute(self):
        # 1. 签到请求
        post_headers = {
            'x-requested-with': 'XMLHttpRequest',
            'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'accept': 'application/json, text/plain, */*'
        }

        check_status = "失败"
        is_success = False

        try:
            resp = self.session.post(url=self.check_url, headers=post_headers, timeout=15)
            if resp.status_code == 200:
                try:
                    result = resp.json()
                    msg = result.get('msg', '')
                    if result.get('ret') == 1:
                        reward = self.extract_reward(msg, result)
                        check_status = f"成功 (+{reward})" if reward else "成功"
                        is_success = True
                    elif "已经签到" in msg or "already" in msg.lower() or result.get('ret') == 0:
                        check_status = "今日已签"
                        is_success = True
                    else:
                        check_status = f"失败({msg})"
                except json.JSONDecodeError:
                    check_status = "Cookie失效"
            else:
                check_status = f"HTTP {resp.status_code}"
        except Exception as e:
            check_status = f"连接异常: {e}"

        # 2. 获取最新流量
        traffic = self.fetch_user_traffic()
        rest_str = f" | 剩余: {traffic['rest']}" if "rest" in traffic else ""
        today_str = f" (今日已用 {traffic['today']})" if "today" in traffic else ""

        # 3. 单行紧凑输出
        log_line = f"[{self.index:02d}] {self.email} -> {check_status}{rest_str}{today_str}"
        print(f"  {'✅' if is_success else '❌'} {log_line}")

        return is_success, f"{'✅' if is_success else '❌'} {log_line}"


def main():
    print(f"==== ikuuu 签到开始 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ====")

    config = load_config()
    accounts = load_accounts()

    if not accounts:
        print("❌ 未在 accounts.json 中找到任何有效 Cookie，退出运行")
        return

    base_url = config.get("base_url")
    interval_min = int(config.get("interval_min", 2))
    interval_max = int(config.get("interval_max", 5))

    print(f"🌐 站点地址: {base_url}")
    print(f"👥 共读取到 {len(accounts)} 个有效账号\n")

    # ---------------- 1. 启动前随机延时 ----------------
    start_delay_max = int(config.get("start_random_delay_max", 0))
    if start_delay_max > 0:
        delay = random.randint(5, start_delay_max)
        print(f"🎲 启动随机休眠: {delay} 秒...")
        time.sleep(delay)

    success_count = 0
    total_count = len(accounts)
    summary_lines = []

    # ---------------- 2. 账号遍历与休眠 ----------------
    for index, acc in enumerate(accounts, start=1):
        if index > 1:
            delay = random.uniform(interval_min, interval_max)
            print(f"⏱️ 休眠 {delay:.1f} 秒处理下一账号...")
            time.sleep(delay)

        signer = IkuuuCookieSigner(
            cookie=acc["cookie"],
            base_url=base_url,
            index=index
        )
        is_success, log_line = signer.execute()

        if is_success:
            success_count += 1
        summary_lines.append(log_line)

    # 简明汇总
    summary_header = f"==== 签到完成: 成功 {success_count}/{total_count} ===="
    print(f"\n{summary_header}")
    summary_content = "\n".join(summary_lines)

    if hadsend:
        notify_title = f"ikuuu签到 ({success_count}/{total_count})"
        notify_user(notify_title, f"{summary_header}\n\n{summary_content}")


if __name__ == "__main__":
    main()
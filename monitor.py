#!/usr/bin/env python3
"""
QMQ 广州 B2 美签可用性监控脚本
每5分钟由 GitHub Actions 触发，检查广州 B2 Visitor Visas 在8月和9月的可用日期。
发现可用日期时通过 QQ 邮箱 SMTP 发送邮件通知。
"""

import json
import os
import smtplib
import ssl
import urllib.request
from email.mime.text import MIMEText
from datetime import datetime

# ============ 配置 ============
SUPABASE_URL = "https://sdetncywjtheyqwfzshc.supabase.co/rest/v1/slot_data"
SUPABASE_KEY = "sb_publishable_lq9TdbQ0wW1tgbKmYyPXsA_YilcZ8an"
CITY_KEY = "cnGUA"  # 广州
VISA_CLASS = "B2 Visitor Visas for Business and Pleasure \u2022 All Others"
TARGET_MONTHS = ["2026-08", "2026-09"]

SMTP_SERVER = "smtp.qq.com"
SMTP_PORT = 465
SMTP_USER = os.environ.get("SMTP_USER", "327241819@qq.com")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
TO_EMAIL = os.environ.get("TO_EMAIL", "327241819@qq.com")


def fetch_slot_data():
    """查询 Supabase API 获取广州 B2 可用日期数据"""
    import urllib.parse
    params = urllib.parse.urlencode({
        "select": "data",
        "city_key": f"eq.{CITY_KEY}",
        "visa_class": f"eq.{VISA_CLASS}",
    })
    url = f"{SUPABASE_URL}?{params}"
    req = urllib.request.Request(url)
    req.add_header("apikey", SUPABASE_KEY)
    req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")

    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def check_available_dates(data):
    """从返回数据中筛选8月和9月的可用日期"""
    available = []
    for record in data:
        slots = record.get("data", {}).get("slots", {})
        for date_str in slots.keys():
            for month in TARGET_MONTHS:
                if date_str.startswith(month):
                    available.append(date_str)
    return sorted(set(available))


def send_email(available_dates):
    """通过 QQ 邮箱 SMTP 发送通知邮件"""
    dates_str = "\n".join(f"  \u2022 {d}" for d in available_dates)
    body = (
        f"广州B2\uff08B2 Visitor Visas for Business and Pleasure \u2022 All Others\uff09"
        f"\u6709\u53ef\u7528\u65e5\u671f\uff01\n\n"
        f"\u53ef\u7528\u65e5\u671f\u5217\u8868\uff1a\n{dates_str}\n\n"
        f"\u8bf7\u5c3d\u5feb\u524d\u5f80\u67e5\u770b\uff1ahttps://qmq.app/\n\n"
        f"\u672c\u90ae\u4ef6\u7531 GitHub Actions \u81ea\u52a8\u53d1\u9001\uff0c"
        f"\u5982\u9700\u505c\u6b62\u901a\u77e5\uff0c\u8bf7\u5728 GitHub \u4ed3\u5e93 Actions \u9875\u9762\u7981\u7528\u5de5\u4f5c\u6d41\u3002\n"
        f"\u53d1\u9001\u65f6\u95f4\uff1a{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = "\u5e7f\u5ddeB2\u7f8e\u7b7e\u53ef\u7528\u901a\u77e5"
    msg["From"] = SMTP_USER
    msg["To"] = TO_EMAIL

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, context=context) as server:
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_USER, [TO_EMAIL], msg.as_string())


def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] \u5f00\u59cb\u68c0\u67e5\u5e7f\u5ddeB2\u53ef\u7528\u65e5\u671f...")

    try:
        data = fetch_slot_data()
    except Exception as e:
        print(f"API \u8bf7\u6c42\u5931\u8d25: {e}")
        return

    if not data:
        print("\u672a\u83b7\u53d6\u5230\u6570\u636e\uff0c\u7b49\u5f85\u4e0b\u4e00\u6b21\u8f6e\u8be2")
        return

    available_dates = check_available_dates(data)

    if not available_dates:
        print("\u5e7f\u5ddeB2 \u57282026\u5e748\u6708\u548c9\u6708\u65e0\u53ef\u7528\u65e5\u671f\uff0c\u7ee7\u7eed\u76d1\u63a7")
        return

    print(f"\u53d1\u73b0 {len(available_dates)} \u4e2a\u53ef\u7528\u65e5\u671f: {available_dates}")

    if not SMTP_PASS:
        print("\u8b66\u544a: SMTP_PASS \u672a\u8bbe\u7f6e\uff0c\u65e0\u6cd5\u53d1\u9001\u90ae\u4ef6")
        return

    try:
        send_email(available_dates)
        print(f"\u90ae\u4ef6\u5df2\u53d1\u9001\u81f3 {TO_EMAIL}")
    except Exception as e:
        print(f"\u90ae\u4ef6\u53d1\u9001\u5931\u8d25: {e}")


if __name__ == "__main__":
    main()

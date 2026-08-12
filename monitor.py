#!/usr/bin/env python3
"""
QMQ 广州 B2 美签可用性监控脚本
- 每3分钟由 GitHub Actions 触发，检查广州 B2 在8月和9月的可用日期。
  仅当出现"新增"可用日期（6小时内未通知过的）时才发邮件，避免重复通知。
  已通知日期的状态记录保存6小时，过期后可再次通知。
- 每3小时整点触发状态报告，发送当前所有可用日期，确认监控正常运行。
"""

import json
import os
import sys
import smtplib
import ssl
import urllib.request
import urllib.parse
from email.mime.text import MIMEText
from email.utils import formataddr
from datetime import datetime, timezone, timedelta

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

STATE_FILE = "notified_state.json"
NOTIFY_COOLDOWN_HOURS = 6  # 已通知日期的冷却时间，超过后可再次通知

CST = timezone(timedelta(hours=8))


# ============ 数据获取 ============

def fetch_slot_data():
    """查询 Supabase API 获取广州 B2 可用日期数据"""
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


def get_all_dates(data):
    """获取所有可用日期（不限月份）"""
    all_dates = []
    for record in data:
        slots = record.get("data", {}).get("slots", {})
        all_dates.extend(slots.keys())
    return sorted(set(all_dates))


def get_target_dates(data):
    """从返回数据中筛选8月和9月的可用日期"""
    all_dates = get_all_dates(data)
    return [d for d in all_dates if any(d.startswith(m) for m in TARGET_MONTHS)]


def get_data_timestamp(data):
    """获取数据更新时间戳"""
    for record in data:
        ts = record.get("data", {}).get("timestamp", 0)
        if ts:
            return datetime.fromtimestamp(ts, tz=CST)
    return None


# ============ 状态管理 ============

def load_notified_state():
    """加载已通知日期状态记录"""
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_notified_state(state):
    """保存已通知日期状态记录到文件"""
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def cleanup_expired_state(state):
    """清理超过冷却时间的记录，返回 (清理后的state, 过期的日期列表)"""
    now = datetime.now(CST)
    cleaned = {}
    expired = []
    for date_str, notified_iso in state.items():
        try:
            notified_time = datetime.fromisoformat(notified_iso)
            if (now - notified_time).total_seconds() < NOTIFY_COOLDOWN_HOURS * 3600:
                cleaned[date_str] = notified_iso
            else:
                expired.append(date_str)
        except Exception:
            expired.append(date_str)
    return cleaned, expired


# ============ 邮件发送 ============

def send_alert_email(new_dates, all_target_dates):
    """发送新增可用日期通知邮件"""
    new_dates_str = "\n".join(f"  \u2022 {d}" for d in new_dates)
    all_dates_str = "\n".join(f"  \u2022 {d}" for d in all_target_dates)
    now_str = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")

    body = (
        f"\u5e7f\u5ddeB2\uff08B2 Visitor Visas for Business and Pleasure \u2022 All Others\uff09"
        f"\u68c0\u6d4b\u5230\u65b0\u589e\u53ef\u7528\u65e5\u671f\uff01\n\n"
        f"========================================\n"
        f"  \u65b0\u589e\u53ef\u7528\u65e5\u671f\uff08\u672c\u6b21\u901a\u77e5\uff09\uff1a\n"
        f"========================================\n"
        f"{new_dates_str}\n\n"
        f"----------------------------------------\n"
        f"  8/9\u6708\u5168\u90e8\u53ef\u7528\u65e5\u671f\uff08\u5171{len(all_target_dates)}\u5929\uff09\uff1a\n"
        f"----------------------------------------\n"
        f"{all_dates_str}\n\n"
        f"\u8bf7\u5c3d\u5feb\u524d\u5f80\u67e5\u770b\uff1ahttps://qmq.app/\n\n"
        f"\u8bf4\u660e\uff1a\u5df2\u901a\u77e5\u8fc7\u7684\u65e5\u671f\u57286\u5c0f\u65f6\u5185\u4e0d\u4f1a\u91cd\u590d\u901a\u77e5\u3002\n"
        f"\u53d1\u9001\u65f6\u95f4\uff1a{now_str}\n"
        f"\u672c\u90ae\u4ef6\u7531 GitHub Actions \u81ea\u52a8\u53d1\u9001\u3002\n"
    )

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = "\u5e7f\u5ddeB2\u7f8e\u7b7e\u53ef\u7528\u901a\u77e5"
    msg["From"] = formataddr(("QMQ Monitor", SMTP_USER))
    msg["To"] = TO_EMAIL

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, context=context) as server:
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_USER, [TO_EMAIL], msg.as_string())


def send_status_email(data, notified_state):
    """发送3小时固定状态报告邮件（无论是否有可用日期都发送）"""
    all_dates = get_all_dates(data)
    target_dates = [d for d in all_dates if any(d.startswith(m) for m in TARGET_MONTHS)]
    ts = get_data_timestamp(data)
    ts_str = ts.strftime("%Y-%m-%d %H:%M:%S") if ts else "\u672a\u77e5"
    now_str = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")

    if all_dates:
        dates_str = "\n".join(f"  \u2022 {d}" for d in all_dates)
    else:
        dates_str = "  \uff08\u6682\u65e0\u53ef\u7528\u65e5\u671f\uff09"

    aug_count = len([d for d in all_dates if d.startswith("2026-08")])
    sep_count = len([d for d in all_dates if d.startswith("2026-09")])

    notified_keys = sorted(notified_state.keys()) if notified_state else []
    if notified_keys:
        notified_str = "\n".join(
            f"  \u2022 {d} (\u5df2\u901a\u77e5\u4e8e {notified_state[d][:19]})"
            for d in notified_keys
        )
    else:
        notified_str = "  \uff08\u65e0\uff09"

    body = (
        f"\u8fd9\u662f\u4e91\u7aef\u76d1\u63a7\u7684\u5b9a\u65f6\u72b6\u6001\u62a5\u544a\uff0c\u8868\u793a\u76d1\u63a7\u6b63\u5728\u6b63\u5e38\u8fd0\u884c\u3002\n\n"
        f"========================================\n"
        f"  \u5e7f\u5dde B2 \u7f8e\u7b7e\u76d1\u63a7\u72b6\u6001\u62a5\u544a\n"
        f"========================================\n\n"
        f"\u7b7e\u8bc1\u7c7b\u522b\uff1aB2 Visitor Visas for Business and Pleasure \u2022 All Others\n"
        f"\u5730\u533a\uff1a\u5e7f\u5dde\n"
        f"\u6570\u636e\u66f4\u65b0\u65f6\u95f4\uff1a{ts_str}\n"
        f"\u62a5\u544a\u53d1\u9001\u65f6\u95f4\uff1a{now_str}\n\n"
        f"----------------------------------------\n"
        f"\u5f53\u524d\u5168\u90e8\u53ef\u7528\u65e5\u671f\uff08\u5171{len(all_dates)}\u5929\uff09\uff1a\n"
        f"{dates_str}\n\n"
        f"----------------------------------------\n"
        f"\u76d1\u63a7\u76ee\u6807\u6708\u4efd\u72b6\u6001\uff1a\n"
        f"  2026\u5e748\u6708\uff1a{aug_count} \u5929\u53ef\u7528\n"
        f"  2026\u5e749\u6708\uff1a{sep_count} \u5929\u53ef\u7528\n\n"
    )

    if target_dates:
        body += (
            f"\u26a0\ufe0f \u6ce8\u610f\uff1a\u76d1\u63a7\u76ee\u6807\u6708\u4efd\u6709\u53ef\u7528\u65e5\u671f\uff01\n"
            f"\u53ef\u7528\u65e5\u671f\uff1a{', '.join(target_dates)}\n\n"
        )
    else:
        body += "\u76d1\u63a7\u76ee\u6807\u6708\u4efd\uff088\u6708\u30019\u6708\uff09\u6682\u65e0\u53ef\u7528\u65e5\u671f\uff0c\u7ee7\u7eed\u76d1\u63a7\u4e2d\u3002\n\n"

    body += (
        f"----------------------------------------\n"
        f"\u5df2\u901a\u77e5\u65e5\u671f\u8bb0\u5f55\uff086\u5c0f\u65f6\u5185\uff0c\u4e0d\u91cd\u590d\u901a\u77e5\uff09\uff1a\n"
        f"{notified_str}\n\n"
        f"----------------------------------------\n"
        f"\u7f51\u7ad9\u94fe\u63a5\uff1ahttps://qmq.app/\n"
        f"\u8fd0\u884c\u9891\u7387\uff1a\u76d1\u63a7\u6bcf3\u5206\u949f\uff0c\u72b6\u6001\u62a5\u544a\u6bcf3\u5c0f\u65f6\n"
        f"\u901a\u77e5\u7b56\u7565\uff1a\u4ec5\u5bf9\u65b0\u589e\u53ef\u7528\u65e5\u671f\u53d1\u90ae\u4ef6\uff0c\u5df2\u901a\u77e5\u7684\u65e5\u671f6\u5c0f\u65f6\u5185\u4e0d\u91cd\u590d\n"
        f"\u672c\u90ae\u4ef6\u7531 GitHub Actions \u81ea\u52a8\u53d1\u9001\u3002\n"
    )

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = "\u5e7f\u5ddeB2\u7f8e\u7b7e3\u5c0f\u65f6\u56fa\u5b9a\u901a\u77e5"
    msg["From"] = formataddr(("QMQ Monitor", SMTP_USER))
    msg["To"] = TO_EMAIL

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, context=context) as server:
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_USER, [TO_EMAIL], msg.as_string())


# ============ 主逻辑 ============

def run_monitor():
    """3分钟监控模式：仅对新增可用日期发邮件，已通知的6小时内不重复"""
    now_str = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now_str}] \u5f00\u59cb\u68c0\u67e5\u5e7f\u5ddeB2\u53ef\u7528\u65e5\u671f...")

    try:
        data = fetch_slot_data()
    except Exception as e:
        print(f"API \u8bf7\u6c42\u5931\u8d25: {e}")
        return

    if not data:
        print("\u672a\u83b7\u53d6\u5230\u6570\u636e\uff0c\u7b49\u5f85\u4e0b\u4e00\u6b21\u8f6e\u8be2")
        return

    target_dates = get_target_dates(data)

    if not target_dates:
        all_dates = get_all_dates(data)
        print(f"\u5e7f\u5ddeB2 \u57282026\u5e748\u6708\u548c9\u6708\u65e0\u53ef\u7528\u65e5\u671f\uff0c"
              f"\u5f53\u524d\u5176\u4ed6\u53ef\u7528\u65e5\u671f{len(all_dates)}\u5929\uff0c\u7ee7\u7eed\u76d1\u63a7")
        return

    # 加载已通知状态并清理过期记录
    state = load_notified_state()
    state, expired = cleanup_expired_state(state)

    if expired:
        print(f"\u5df2\u8fc7\u671f\uff08\u8d856\u5c0f\u65f6\uff09\u7684\u8bb0\u5f55: {expired}\uff0c\u53ef\u91cd\u65b0\u901a\u77e5")

    # 找出新增日期：在当前可用日期中，但不在已通知记录中（或已过期被清理）
    new_dates = [d for d in target_dates if d not in state]

    print(f"\u5f53\u524d8/9\u6708\u53ef\u7528\u65e5\u671f: {target_dates}")
    print(f"\u5df2\u901a\u77e5\uff086\u5c0f\u65f6\u5185\uff09: {sorted(state.keys())}")
    print(f"\u65b0\u589e\u53ef\u7528\u65e5\u671f: {new_dates}")

    if not new_dates:
        print("\u65e0\u65b0\u589e\u53ef\u7528\u65e5\u671f\uff0c\u4e0d\u53d1\u9001\u901a\u77e5")
        # 仍然保存清理后的状态（移除过期记录）
        save_notified_state(state)
        return

    print(f"\u53d1\u73b0 {len(new_dates)} \u4e2a\u65b0\u589e\u53ef\u7528\u65e5\u671f: {new_dates}")

    if not SMTP_PASS:
        print("\u8b66\u544a: SMTP_PASS \u672a\u8bbe\u7f6e\uff0c\u65e0\u6cd5\u53d1\u9001\u90ae\u4ef6")
        return

    try:
        send_alert_email(new_dates, target_dates)
        print(f"\u65b0\u589e\u53ef\u7528\u901a\u77e5\u90ae\u4ef6\u5df2\u53d1\u9001\u81f3 {TO_EMAIL}")

        # 更新状态：将新通知的日期加入记录
        now_iso = datetime.now(CST).isoformat()
        for d in new_dates:
            state[d] = now_iso

        save_notified_state(state)
        print(f"\u5df2\u66f4\u65b0\u901a\u77e5\u72b6\u6001\u8bb0\u5f55: {sorted(state.keys())}")
    except Exception as e:
        print(f"\u90ae\u4ef6\u53d1\u9001\u5931\u8d25: {e}")


def run_status():
    """3小时状态报告模式：无论是否有可用日期都发邮件"""
    now_str = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now_str}] \u53d1\u90013\u5c0f\u65f6\u56fa\u5b9a\u72b6\u6001\u62a5\u544a...")

    try:
        data = fetch_slot_data()
    except Exception as e:
        print(f"API \u8bf7\u6c42\u5931\u8d25: {e}")
        if SMTP_PASS:
            try:
                now_str2 = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")
                body = (
                    f"\u4e91\u7aef\u76d1\u63a7\u72b6\u6001\u62a5\u544a\n\n"
                    f"\u53d1\u9001\u65f6\u95f4\uff1a{now_str2}\n"
                    f"\u72b6\u6001\uff1aAPI \u8bf7\u6c42\u5931\u8d25\uff08{e}\uff09\n"
                    f"\u8bf7\u68c0\u67e5 GitHub Actions \u8fd0\u884c\u65e5\u5fd7\u3002\n"
                )
                msg = MIMEText(body, "plain", "utf-8")
                msg["Subject"] = "\u5e7f\u5ddeB2\u7f8e\u7b7e3\u5c0f\u65f6\u56fa\u5b9a\u901a\u77e5"
                msg["From"] = formataddr(("QMQ Monitor", SMTP_USER))
                msg["To"] = TO_EMAIL
                context = ssl.create_default_context()
                with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, context=context) as server:
                    server.login(SMTP_USER, SMTP_PASS)
                    server.sendmail(SMTP_USER, [TO_EMAIL], msg.as_string())
                print(f"\u72b6\u6001\u62a5\u544a\u90ae\u4ef6\u5df2\u53d1\u9001\u81f3 {TO_EMAIL}\uff08API\u5f02\u5e38\uff09")
            except Exception as e2:
                print(f"\u90ae\u4ef6\u53d1\u9001\u4e5f\u5931\u8d25: {e2}")
        return

    if not data:
        print("\u672a\u83b7\u53d6\u5230\u6570\u636e")
        return

    all_dates = get_all_dates(data)
    print(f"\u5f53\u524d\u53ef\u7528\u65e5\u671f{len(all_dates)}\u5929: {all_dates}")

    # 加载已通知状态用于状态报告展示
    state = load_notified_state()
    state, _ = cleanup_expired_state(state)

    if not SMTP_PASS:
        print("\u8b66\u544a: SMTP_PASS \u672a\u8bbe\u7f6e\uff0c\u65e0\u6cd5\u53d1\u9001\u90ae\u4ef6")
        return

    try:
        send_status_email(data, state)
        print(f"\u72b6\u6001\u62a5\u544a\u90ae\u4ef6\u5df2\u53d1\u9001\u81f3 {TO_EMAIL}")
    except Exception as e:
        print(f"\u90ae\u4ef6\u53d1\u9001\u5931\u8d25: {e}")


if __name__ == "__main__":
    if "--status" in sys.argv:
        run_status()
    else:
        run_monitor()

#!/usr/bin/env python3
"""
QMQ 广州 B1+B2 美签可用性监控脚本
- 每5分钟由 GitHub Actions / 本地自动化触发，检查广州 B1 和 B2 在8月和9月的可用日期。
  B1/B2 任一类型出现"新增"可用日期（6小时内未通知过的）即发邮件，避免重复通知。
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

# B1 和 B2 两种签证类型（key 用于状态记录区分）
VISA_CLASSES = {
    "B1": "B1 Visitor Visas for Business and Pleasure \u2022 All Others",
    "B2": "B2 Visitor Visas for Business and Pleasure \u2022 All Others",
}
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

def fetch_visa_data(visa_class):
    """查询 Supabase API 获取指定签证类型在广州的可用日期数据"""
    params = urllib.parse.urlencode({
        "select": "data",
        "city_key": f"eq.{CITY_KEY}",
        "visa_class": f"eq.{visa_class}",
    })
    url = f"{SUPABASE_URL}?{params}"
    req = urllib.request.Request(url)
    req.add_header("apikey", SUPABASE_KEY)
    req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")

    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_all_visa_data():
    """分别查询 B1、B2，返回 {visa_key: supabase_records}，单类型失败不影响另一类型"""
    result = {}
    for key, visa_class in VISA_CLASSES.items():
        try:
            result[key] = fetch_visa_data(visa_class)
            print(f"  {key}: 查询成功 ({len(result[key])} 条记录)")
        except Exception as e:
            print(f"  {key}: 查询失败 {e}")
            result[key] = []
    return result


def get_all_dates(data):
    """获取某类型所有可用日期（不限月份）"""
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
# 状态 key 格式: "B1|2026-09-23" 或 "B2|2026-09-23"，B1/B2 各自独立通知

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
    """清理超过冷却时间的记录，返回 (清理后的state, 过期的key列表)"""
    now = datetime.now(CST)
    cleaned = {}
    expired = []
    for key, notified_iso in state.items():
        try:
            notified_time = datetime.fromisoformat(notified_iso)
            if (now - notified_time).total_seconds() < NOTIFY_COOLDOWN_HOURS * 3600:
                cleaned[key] = notified_iso
            else:
                expired.append(key)
        except Exception:
            expired.append(key)
    return cleaned, expired


# ============ 邮件发送 ============

def format_dates_with_visa(keys):
    """把状态key列表格式化成 'B1 2026-09-23' 形式"""
    return "\n".join(f"  \u2022 {k.replace('|', ' ')}" for k in keys)


def send_alert_email(new_keys, target_by_visa):
    """发送新增可用日期通知邮件（B1/B2 分别展示）"""
    new_dates_str = format_dates_with_visa(new_keys)

    # 按类型组装 8/9 月全部可用日期
    sections = []
    for key in VISA_CLASSES:
        dates = target_by_visa.get(key, [])
        if dates:
            d_str = "\n".join(f"  \u2022 {d}" for d in dates)
        else:
            d_str = "  （暂无）"
        sections.append(f"  [{key}] 共{len(dates)}天：\n{d_str}")
    all_dates_str = "\n\n".join(sections)

    now_str = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")

    body = (
        f"广州 B1/B2（Business and Pleasure • All Others）检测到新增可用日期！\n\n"
        f"========================================\n"
        f"  新增可用日期（本次通知）：\n"
        f"========================================\n"
        f"{new_dates_str}\n\n"
        f"----------------------------------------\n"
        f"  8/9月全部可用日期：\n"
        f"----------------------------------------\n"
        f"{all_dates_str}\n\n"
        f"请尽快前往查看：https://qmq.app/\n\n"
        f"说明：已通知过的日期在6小时内不会重复通知。\n"
        f"发送时间：{now_str}\n"
        f"本邮件由监控系统自动发送。\n"
    )

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = "广州B1/B2美签可用通知"
    msg["From"] = formataddr(("QMQ Monitor", SMTP_USER))
    msg["To"] = TO_EMAIL

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, context=context) as server:
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_USER, [TO_EMAIL], msg.as_string())


def send_status_email(visa_data, notified_state):
    """发送3小时固定状态报告邮件（无论是否有可用日期都发送）"""
    now_str = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")

    # 每种类型分别展示
    all_dates_total = 0
    sections = []
    for key in VISA_CLASSES:
        data = visa_data.get(key, [])
        all_dates = get_all_dates(data) if data else []
        target_dates = [d for d in all_dates if any(d.startswith(m) for m in TARGET_MONTHS)]
        all_dates_total += len(all_dates)
        aug_count = len([d for d in all_dates if d.startswith("2026-08")])
        sep_count = len([d for d in all_dates if d.startswith("2026-09")])
        if all_dates:
            d_str = "\n".join(f"  \u2022 {d}" for d in all_dates)
        else:
            d_str = "  （暂无可用日期）"
        warn = f"  ⚠️ 目标月份有可用日期: {', '.join(target_dates)}" if target_dates else ""
        sections.append(
            f"----- {key} ({VISA_CLASSES[key]}) -----\n"
            f"  全部可用日期（共{len(all_dates)}天）：\n{d_str}\n"
            f"  2026年8月: {aug_count} 天 | 2026年9月: {sep_count} 天\n{warn}"
        )
    visa_summary = "\n\n".join(sections)

    # 已通知记录展示
    notified_keys = sorted(notified_state.keys()) if notified_state else []
    if notified_keys:
        notified_str = "\n".join(
            f"  \u2022 {k.replace('|', ' ')} (已通知于 {notified_state[k][:19]})"
            for k in notified_keys
        )
    else:
        notified_str = "  （无）"

    # 数据更新时间（任一类型）
    ts = None
    for key in VISA_CLASSES:
        ts = get_data_timestamp(visa_data.get(key, []))
        if ts:
            break
    ts_str = ts.strftime("%Y-%m-%d %H:%M:%S") if ts else "未知"

    body = (
        f"这是云端监控的定时状态报告，表示监控正在正常运行。\n\n"
        f"========================================\n"
        f"  广州 B1/B2 美签监控状态报告\n"
        f"========================================\n\n"
        f"监测类型：B1 + B2（Business and Pleasure • All Others）\n"
        f"地区：广州\n"
        f"数据更新时间：{ts_str}\n"
        f"报告发送时间：{now_str}\n\n"
        f"----------------------------------------\n"
        f"各类型可用日期（总计{all_dates_total}天）：\n"
        f"----------------------------------------\n"
        f"{visa_summary}\n\n"
    )

    # 目标月份是否有可用日期
    target_any = []
    for key in VISA_CLASSES:
        data = visa_data.get(key, [])
        target_any.extend(get_target_dates(data) if data else [])
    if target_any:
        body += (
            f"⚠️ 注意：监控目标月份（8月、9月）有可用日期！\n"
            f"可用日期：{', '.join(sorted(set(target_any)))}\n\n"
        )
    else:
        body += "监控目标月份（8月、9月）暂无可用日期，继续监控中。\n\n"

    body += (
        f"----------------------------------------\n"
        f"已通知日期记录（6小时内，不重复通知）：\n"
        f"{notified_str}\n\n"
        f"----------------------------------------\n"
        f"网站链接：https://qmq.app/\n"
        f"运行频率：监控每5分钟，状态报告每3小时\n"
        f"通知策略：仅对新增可用日期发邮件，已通知的日期6小时内不重复\n"
        f"本邮件由监控系统自动发送。\n"
    )

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = "广州B1/B2美签3小时固定通知"
    msg["From"] = formataddr(("QMQ Monitor", SMTP_USER))
    msg["To"] = TO_EMAIL

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, context=context) as server:
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_USER, [TO_EMAIL], msg.as_string())


# ============ 主逻辑 ============

def run_monitor():
    """5分钟监控模式：B1/B2 任一类型出现新增可用日期即发邮件，6小时内不重复"""
    now_str = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now_str}] 开始检查广州 B1+B2 可用日期...")

    visa_data = fetch_all_visa_data()

    # 汇总每种类型的目标月份可用日期
    target_by_visa = {}   # {"B1": [...], "B2": [...]}
    all_dates_by_visa = {}
    for key in VISA_CLASSES:
        data = visa_data.get(key, [])
        if data:
            all_dates_by_visa[key] = get_all_dates(data)
            target_by_visa[key] = get_target_dates(data)
        else:
            all_dates_by_visa[key] = []
            target_by_visa[key] = []

    total_target = sum(len(v) for v in target_by_visa.values())
    if total_target == 0:
        for key in VISA_CLASSES:
            print(f"  {key}: 2026年8月和9月无可用日期，当前其他可用日期"
                  f"{len(all_dates_by_visa[key])}天")
        print("继续监控")
        return

    # 加载已通知状态并清理过期记录
    state = load_notified_state()
    state, expired = cleanup_expired_state(state)

    if expired:
        print(f"已过期（超过6小时）的记录: {expired}，可重新通知")

    # 找出新增：当前可用日期中，不在已通知记录里的（key 为 "B1|日期" / "B2|日期"）
    new_keys = []
    for key in VISA_CLASSES:
        for d in target_by_visa[key]:
            state_key = f"{key}|{d}"
            if state_key not in state:
                new_keys.append(state_key)

    print(f"当前8/9月可用: {target_by_visa}")
    print(f"已通知（6小时内）: {sorted(state.keys())}")
    print(f"新增可用: {new_keys}")

    if not new_keys:
        print("无新增可用日期，不发送通知")
        save_notified_state(state)  # 保存清理后的状态（移除过期记录）
        return

    print(f"发现 {len(new_keys)} 个新增可用日期: {new_keys}")

    if not SMTP_PASS:
        print("警告: SMTP_PASS 未设置，无法发送邮件")
        return

    try:
        send_alert_email(new_keys, target_by_visa)
        print(f"新增可用通知邮件已发送至 {TO_EMAIL}")

        # 更新状态：将新通知的日期加入记录
        now_iso = datetime.now(CST).isoformat()
        for k in new_keys:
            state[k] = now_iso

        save_notified_state(state)
        print(f"已更新通知状态记录: {sorted(state.keys())}")
    except Exception as e:
        print(f"邮件发送失败: {e}")


def run_status():
    """3小时状态报告模式：无论是否有可用日期都发邮件"""
    now_str = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now_str}] 发送3小时固定状态报告...")

    visa_data = fetch_all_visa_data()

    # 若全部类型都查询失败，则发一封异常说明邮件
    if not any(visa_data.values()):
        print("所有类型 API 请求均失败")
        if SMTP_PASS:
            try:
                now_str2 = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")
                body = (
                    f"云端监控状态报告\n\n"
                    f"发送时间：{now_str2}\n"
                    f"状态：B1/B2 API 请求均失败\n"
                    f"请检查运行日志。\n"
                )
                msg = MIMEText(body, "plain", "utf-8")
                msg["Subject"] = "广州B1/B2美签3小时固定通知"
                msg["From"] = formataddr(("QMQ Monitor", SMTP_USER))
                msg["To"] = TO_EMAIL
                context = ssl.create_default_context()
                with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, context=context) as server:
                    server.login(SMTP_USER, SMTP_PASS)
                    server.sendmail(SMTP_USER, [TO_EMAIL], msg.as_string())
                print(f"状态报告邮件已发送至 {TO_EMAIL}（API异常）")
            except Exception as e2:
                print(f"邮件发送也失败: {e2}")
        return

    for key in VISA_CLASSES:
        data = visa_data.get(key, [])
        if data:
            print(f"  {key}: 当前可用日期 {len(get_all_dates(data))} 天")

    # 加载已通知状态用于状态报告展示
    state = load_notified_state()
    state, _ = cleanup_expired_state(state)

    if not SMTP_PASS:
        print("警告: SMTP_PASS 未设置，无法发送邮件")
        return

    try:
        send_status_email(visa_data, state)
        print(f"状态报告邮件已发送至 {TO_EMAIL}")
    except Exception as e:
        print(f"邮件发送失败: {e}")


if __name__ == "__main__":
    if "--status" in sys.argv:
        run_status()
    else:
        run_monitor()

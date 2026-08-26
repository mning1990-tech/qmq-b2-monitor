#!/usr/bin/env python3
"""诊断脚本：在 GitHub Actions 环境测试 cal-view 端点被 401 的原因"""
import urllib.request
import urllib.error
import json

CAL_VIEW_URL = "https://sdetncywjtheyqwfzshc.supabase.co/functions/v1/cal-view"
SUPABASE_KEY = "sb_publishable_lq9TdbQ0wW1tgbKmYyPXsA_YilcZ8an"

print("=" * 60)
print("测试 0: Runner 出口 IP 及归属地")
print("=" * 60)
try:
    with urllib.request.urlopen("https://api.ipify.org?format=json", timeout=15) as resp:
        ip = json.loads(resp.read().decode())["ip"]
    print(f"出口 IP: {ip}")
    with urllib.request.urlopen(f"http://ip-api.com/json/{ip}", timeout=15) as resp:
        geo = json.loads(resp.read().decode())
    print(f"归属: {geo.get('country')} {geo.get('regionName')} {geo.get('city')} | ISP: {geo.get('isp')} | Org: {geo.get('org')}")
except Exception as e:
    print(f"IP 查询失败: {e}")


def test_request(label, extra_headers=None, method="GET"):
    print()
    print("=" * 60)
    print(f"测试: {label}")
    print("=" * 60)
    req = urllib.request.Request(CAL_VIEW_URL, method=method)
    req.add_header("apikey", SUPABASE_KEY)
    req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
    if extra_headers:
        for k, v in extra_headers.items():
            req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read()
            print(f"结果: {resp.status} OK, 响应 {len(body)} 字节")
            print(f"Server: {resp.headers.get('server')} | x-edge: {resp.headers.get('x-sb-edge-region')}")
            print(f"前 150 字符: {body[:150].decode('utf-8', errors='replace')}")
            return True
    except urllib.error.HTTPError as e:
        body = e.read()
        print(f"结果: HTTP {e.code} {e.reason}")
        print(f"响应头: {dict(e.headers)}")
        print(f"响应体: {body[:500].decode('utf-8', errors='replace')}")
        return False
    except Exception as e:
        print(f"结果: {type(e).__name__}: {e}")
        return False


# 测试 1: 完全复刻 monitor.py 的请求（预期 401）
test_request("1. 当前 monitor.py 的请求方式（无额外头）")

# 测试 2: 浏览器伪装头（Origin + Referer + UA）
test_request("2. 浏览器伪装头（Origin/Referer/Chrome UA）", {
    "Origin": "https://qmq.app",
    "Referer": "https://qmq.app/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "zh-CN,zh;q=0.9",
})

# 测试 3: 仅加 User-Agent
test_request("3. 仅 Chrome User-Agent（无 Origin/Referer）", {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
})

# 测试 4: OPTIONS 预检请求
test_request("4. OPTIONS 预检", {
    "Origin": "https://qmq.app",
    "Access-Control-Request-Method": "GET",
}, method="OPTIONS")

print()
print("=" * 60)
print("诊断完成")
print("=" * 60)

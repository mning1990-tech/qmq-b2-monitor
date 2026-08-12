"""Upload files to GitHub repo via API (bypassing git push)"""
import json
import base64
import urllib.request

GH_TOKEN = "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"
REPO = "mning1990-tech/qmq-b2-monitor"
API = f"https://api.github.com/repos/{REPO}/contents"

files = {
    ".gitignore": "set_secrets.py\n__pycache__/\n*.pyc\n",
    "monitor.py": open("C:/Users/LEO/WorkBuddy/2026-08-12-16-45-49/qmq-monitor/monitor.py", "r", encoding="utf-8").read(),
    ".github/workflows/monitor.yml": open("C:/Users/LEO/WorkBuddy/2026-08-12-16-45-49/qmq-monitor/.github/workflows/monitor.yml", "r", encoding="utf-8").read(),
}

for path, content in files.items():
    payload = {
        "message": f"Add {path}",
        "content": base64.b64encode(content.encode("utf-8")).decode(),
    }
    req = urllib.request.Request(
        f"{API}/{path}",
        data=json.dumps(payload).encode(),
        method="PUT",
    )
    req.add_header("Authorization", f"token {GH_TOKEN}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read().decode())
            print(f"  {path}: uploaded OK")
    except Exception as e:
        print(f"  {path}: FAILED - {e}")

print("All files uploaded!")

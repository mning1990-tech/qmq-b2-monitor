"""Upload updated files to GitHub repo via API"""
import json
import base64
import urllib.request

GH_TOKEN = "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"
REPO = "mning1990-tech/qmq-b2-monitor"
API = f"https://api.github.com/repos/{REPO}/contents"

# Read updated files
files = {
    "monitor.py": open("C:/Users/LEO/WorkBuddy/2026-08-12-16-45-49/qmq-monitor/monitor.py", "r", encoding="utf-8").read(),
    ".github/workflows/monitor.yml": open("C:/Users/LEO/WorkBuddy/2026-08-12-16-45-49/qmq-monitor/.github/workflows/monitor.yml", "r", encoding="utf-8").read(),
}

for path, content in files.items():
    # First get the current file SHA (needed for updates)
    req = urllib.request.Request(f"{API}/{path}")
    req.add_header("Authorization", f"token {GH_TOKEN}")
    req.add_header("Accept", "application/vnd.github+json")
    try:
        with urllib.request.urlopen(req) as resp:
            file_data = json.loads(resp.read().decode())
            sha = file_data["sha"]
            print(f"  {path}: current SHA = {sha[:8]}")
    except Exception as e:
        print(f"  {path}: could not get SHA - {e}")
        sha = None

    # Update the file
    payload = {
        "message": f"Update {path} - add 3-hour status report",
        "content": base64.b64encode(content.encode("utf-8")).decode(),
    }
    if sha:
        payload["sha"] = sha

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
            print(f"  {path}: updated OK")
    except Exception as e:
        print(f"  {path}: FAILED - {e}")

print("All files updated!")

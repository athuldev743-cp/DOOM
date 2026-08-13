import os
import requests


def trigger_github_workflow(workflow_file: str = "platform-apply.yml", ref: str = "main") -> bool:
    """Fires GitHub's workflow_dispatch API so the platform-apply worker runs
    immediately instead of waiting for its scheduled cron."""
    token = os.getenv("GITHUB_PAT")
    owner = os.getenv("GITHUB_REPO_OWNER")
    repo = os.getenv("GITHUB_REPO_NAME")

    if not (token and owner and repo):
        print("[GitHub Trigger] Missing GITHUB_PAT / GITHUB_REPO_OWNER / GITHUB_REPO_NAME env vars.")
        return False

    url = f"https://api.github.com/repos/{owner}/{repo}/actions/workflows/{workflow_file}/dispatches"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }
    try:
        resp = requests.post(url, headers=headers, json={"ref": ref}, timeout=10)
        return resp.status_code == 204
    except Exception as e:
        print(f"[GitHub Trigger] Failed: {e}")
        return False
"""Apprentice — GitHub and Jenkins integration (read-only)."""
import json
from typing import Optional

from . import settings_manager


def _settings():
    return settings_manager.load_settings()


# ── GitHub ───────────────────────────────────────────────────

def get_pr_status(repo_full_name: str, pr_number: int) -> dict:
    """Return PR status dict: state, mergeable, title, head_sha, checks."""
    try:
        from github import Github, GithubException
    except ImportError:
        raise RuntimeError("PyGithub not installed. Run: pip install PyGithub")

    token = _settings().get("github_token", "").strip()
    if not token:
        raise RuntimeError("GitHub token not configured in Apprentice settings")

    gh = Github(token)
    try:
        repo = gh.get_repo(repo_full_name)
        pr = repo.get_pull(pr_number)
        commit = repo.get_commit(pr.head.sha)
        checks = [
            {"name": s.context, "state": s.state, "description": s.description}
            for s in commit.get_statuses()
        ]
        return {
            "number": pr.number,
            "title": pr.title,
            "state": pr.state,
            "mergeable": pr.mergeable,
            "head_sha": pr.head.sha,
            "base_branch": pr.base.ref,
            "head_branch": pr.head.ref,
            "checks": checks,
            "url": pr.html_url,
        }
    except GithubException as e:
        raise RuntimeError(f"GitHub API error: {e.status} {e.data}")


def get_pr_review_comments(repo_full_name: str, pr_number: int) -> list:
    """Return list of review comments on a PR."""
    try:
        from github import Github, GithubException
    except ImportError:
        raise RuntimeError("PyGithub not installed. Run: pip install PyGithub")

    token = _settings().get("github_token", "").strip()
    if not token:
        raise RuntimeError("GitHub token not configured in Apprentice settings")

    gh = Github(token)
    try:
        repo = gh.get_repo(repo_full_name)
        pr = repo.get_pull(pr_number)
        comments = []
        for review in pr.get_reviews():
            comments.append({
                "reviewer": review.user.login,
                "state": review.state,
                "body": review.body,
                "submitted_at": review.submitted_at.isoformat() if review.submitted_at else None,
            })
        for comment in pr.get_review_comments():
            comments.append({
                "reviewer": comment.user.login,
                "path": comment.path,
                "line": comment.original_line,
                "body": comment.body,
                "created_at": comment.created_at.isoformat(),
            })
        return comments
    except GithubException as e:
        raise RuntimeError(f"GitHub API error: {e.status} {e.data}")


# ── Jenkins ──────────────────────────────────────────────────

def get_build_result(job_name: str, build_number: int) -> dict:
    """Return build result dict: result, duration, timestamp, url."""
    import requests

    s = _settings()
    jenkins_url = (s.get("jenkins_url") or "").rstrip("/")
    user = s.get("jenkins_user", "")
    token = s.get("jenkins_token", "")
    if not jenkins_url:
        raise RuntimeError("Jenkins URL not configured in Apprentice settings")

    url = f"{jenkins_url}/job/{job_name}/{build_number}/api/json"
    auth = (user, token) if user and token else None
    resp = requests.get(url, auth=auth, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    return {
        "job": job_name,
        "number": build_number,
        "result": data.get("result"),
        "building": data.get("building", False),
        "duration_ms": data.get("duration"),
        "timestamp": data.get("timestamp"),
        "url": data.get("url"),
    }


def get_build_console(job_name: str, build_number: int, max_chars: int = 5000) -> str:
    """Return the last max_chars of a Jenkins build console log."""
    import requests

    s = _settings()
    jenkins_url = (s.get("jenkins_url") or "").rstrip("/")
    user = s.get("jenkins_user", "")
    token = s.get("jenkins_token", "")
    if not jenkins_url:
        raise RuntimeError("Jenkins URL not configured in Apprentice settings")

    url = f"{jenkins_url}/job/{job_name}/{build_number}/consoleText"
    auth = (user, token) if user and token else None
    resp = requests.get(url, auth=auth, timeout=30)
    resp.raise_for_status()
    text = resp.text or ""
    return text[-max_chars:] if len(text) > max_chars else text

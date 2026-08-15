#!/usr/bin/env python3
"""
Pull recent commits from the source repo, update data/commits.json,
and email a summary when new commits appear.

Everything is configured through environment variables (set in the
GitHub Actions workflow from repo Variables/Secrets):

  Required
    SOURCE_OWNER    GitHub owner/org that owns the source repo
    SOURCE_REPO     source repo name (e.g. rutejobs-mj-bladehandling-collab)

  Optional
    SOURCE_BRANCH   branch to track (default: repo default branch)
    GH_TOKEN        token for the GitHub API. Needed only if the source
                    repo is PRIVATE, or to raise the rate limit. A public
                    repo works with no token.
    MAX_KEEP        how many commits to retain in the JSON (default 300)

  Email (all must be set to send mail; otherwise email is skipped)
    SMTP_HOST       default smtp.gmail.com
    SMTP_PORT       default 587
    SMTP_USER       SMTP username (e.g. your Gmail address)
    SMTP_PASS       SMTP password / app password
    MAIL_FROM       from address (default: SMTP_USER)
    MAIL_TO         comma-separated recipient list
"""

import json
import os
import smtplib
import sys
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "commits.json"
API = "https://api.github.com"


def env(name, default=None):
    v = os.environ.get(name)
    return v if v not in (None, "") else default


def gh_get(url, token):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "mj-bladehandling-commit-timeline",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = Request(url, headers=headers)
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_commits(owner, repo, branch, token, per_page=100):
    path = f"{API}/repos/{quote(owner)}/{quote(repo)}/commits?per_page={per_page}"
    if branch:
        path += f"&sha={quote(branch)}"
    raw = gh_get(path, token)
    out = []
    for c in raw:
        commit = c.get("commit", {}) or {}
        author_meta = commit.get("author", {}) or {}
        gh_author = c.get("author") or {}  # may be null for non-GitHub authors
        msg = (commit.get("message") or "").strip().splitlines()
        out.append({
            "sha": c.get("sha", ""),
            "short": (c.get("sha") or "")[:7],
            "message": msg[0] if msg else "(no message)",
            "author": author_meta.get("name") or gh_author.get("login") or "unknown",
            "login": gh_author.get("login") or "",
            "avatar": gh_author.get("avatar_url") or "",
            "date": author_meta.get("date") or commit.get("committer", {}).get("date") or "",
            "url": c.get("html_url", ""),
        })
    return out


def load_existing():
    if DATA_PATH.exists():
        try:
            return json.loads(DATA_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"meta": {}, "commits": []}


def send_email(new_commits, owner, repo):
    host = env("SMTP_HOST", "smtp.gmail.com")
    port = int(env("SMTP_PORT", "587"))
    user = env("SMTP_USER")
    pw = env("SMTP_PASS")
    to = env("MAIL_TO")
    sender = env("MAIL_FROM", user)

    if not (user and pw and to):
        print("email: SMTP_USER / SMTP_PASS / MAIL_TO not all set — skipping email.")
        return

    recipients = [a.strip() for a in to.split(",") if a.strip()]
    n = len(new_commits)
    subject = f"[{repo}] {n} new commit{'s' if n != 1 else ''}"

    rows = ""
    for c in new_commits:
        when = c["date"][:16].replace("T", " ") if c["date"] else ""
        rows += (
            f'<tr>'
            f'<td style="padding:8px 12px;font-family:monospace;color:#46c8bd;">'
            f'<a href="{c["url"]}" style="color:#46c8bd;text-decoration:none;">{c["short"]}</a></td>'
            f'<td style="padding:8px 12px;color:#0e1a20;">{_html(c["message"])}</td>'
            f'<td style="padding:8px 12px;color:#5f7982;white-space:nowrap;">{_html(c["author"])}</td>'
            f'<td style="padding:8px 12px;color:#8ea6ad;white-space:nowrap;">{when}</td>'
            f'</tr>'
        )

    html = f"""\
<div style="font-family:Arial,Helvetica,sans-serif;max-width:640px;margin:auto;">
  <div style="background:#0e1a20;color:#e9efec;padding:18px 22px;border-radius:12px 12px 0 0;">
    <div style="font-family:monospace;font-size:12px;letter-spacing:.15em;color:#46c8bd;">
      REPOSITORY MONITOR</div>
    <div style="font-size:20px;font-weight:700;margin-top:4px;">
      {n} new commit{'s' if n != 1 else ''} in {_html(owner)}/{_html(repo)}</div>
  </div>
  <table style="width:100%;border-collapse:collapse;background:#fff;
                border:1px solid #e2e8e6;border-top:none;">
    {rows}
  </table>
  <p style="font-family:monospace;font-size:11px;color:#8ea6ad;margin-top:14px;">
    Sent by mj-bladehandling-commit-timeline · next check in ~2h</p>
</div>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    plain = "\n".join(f"{c['short']}  {c['message']}  — {c['author']}" for c in new_commits)
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP(host, port, timeout=30) as s:
        s.starttls()
        s.login(user, pw)
        s.sendmail(sender, recipients, msg.as_string())
    print(f"email: sent to {', '.join(recipients)}")


def _html(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def set_action_output(name, value):
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"{name}={value}\n")


def main():
    owner = env("SOURCE_OWNER")
    repo = env("SOURCE_REPO")
    if not (owner and repo):
        print("ERROR: SOURCE_OWNER and SOURCE_REPO must be set.", file=sys.stderr)
        sys.exit(1)

    branch = env("SOURCE_BRANCH")
    token = env("GH_TOKEN")
    max_keep = int(env("MAX_KEEP", "300"))

    try:
        fetched = fetch_commits(owner, repo, branch, token)
    except HTTPError as e:
        detail = "check SOURCE_OWNER/SOURCE_REPO, or set GH_TOKEN if the repo is private" \
            if e.code in (403, 404) else ""
        print(f"ERROR: GitHub API returned {e.code}. {detail}", file=sys.stderr)
        sys.exit(1)
    except URLError as e:
        print(f"ERROR: could not reach GitHub API: {e}", file=sys.stderr)
        sys.exit(1)

    existing = load_existing()
    known = {c["sha"] for c in existing.get("commits", [])}
    new_commits = [c for c in fetched if c["sha"] and c["sha"] not in known]

    # merge, dedupe, sort newest-first, cap length
    by_sha = {c["sha"]: c for c in existing.get("commits", [])}
    for c in fetched:
        if c["sha"]:
            by_sha[c["sha"]] = c
    merged = sorted(by_sha.values(), key=lambda c: c["date"], reverse=True)[:max_keep]

    data = {
        "meta": {
            "source_owner": owner,
            "source_repo": repo,
            "branch": branch or "default",
            "last_sync": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "total": len(merged),
            "generated_by": "mj-bladehandling-commit-timeline",
        },
        "commits": merged,
    }
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATA_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"fetched {len(fetched)} commits · {len(new_commits)} new · {len(merged)} stored")
    set_action_output("new_count", len(new_commits))

    if new_commits:
        # newest-first in the email
        new_commits.sort(key=lambda c: c["date"], reverse=True)
        try:
            send_email(new_commits, owner, repo)
        except Exception as e:  # never fail the whole run because email hiccuped
            print(f"email: failed to send ({e})", file=sys.stderr)
    else:
        print("no new commits — no email sent.")


if __name__ == "__main__":
    main()

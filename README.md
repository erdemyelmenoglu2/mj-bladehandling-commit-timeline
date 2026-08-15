# mj-bladehandling-commit-timeline

A self-updating dashboard that monitors the commit activity of
**`rutejobs-mj-bladehandling-collab`**, renders it as a living visual timeline,
and emails a summary whenever new commits land.

Everything runs on free GitHub infrastructure:

| Piece | Does what | Runs where |
|---|---|---|
| `.github/workflows/monitor.yml` | Every 2h: fetch commits, update data, email | GitHub Actions |
| `scripts/fetch_commits.py` | Talks to the GitHub API, writes `data/commits.json`, sends mail | inside the Action |
| `index.html` | Reads `data/commits.json`, draws the timeline | GitHub Pages |
| `data/commits.json` | The commit record the page reads | committed by the Action |

---

## Setup (one time, ~10 minutes)

### 1. Add these files to the repo

Drop everything in this folder into the root of `mj-bladehandling-commit-timeline`
and push to `main`.

### 2. Point it at the source repo — repo **Variables**

Settings → Secrets and variables → Actions → **Variables** tab → New variable:

| Name | Value |
|---|---|
| `SOURCE_OWNER` | the GitHub user/org that owns the source repo |
| `SOURCE_REPO` | `rutejobs-mj-bladehandling-collab` |
| `SOURCE_BRANCH` | *(optional)* a branch name; leave unset to track the default branch |

> If `rutejobs-mj-bladehandling-collab` is the **full** repo name and the owner is
> separate, `SOURCE_OWNER` is that owner. If you're unsure, open the source repo on
> GitHub — the URL is `github.com/OWNER/REPO`.

### 3. Email — repo **Secrets**

Same page, **Secrets** tab → New secret. For Gmail, create an
[App Password](https://myaccount.google.com/apppasswords) (regular passwords won't work):

| Name | Value |
|---|---|
| `SMTP_USER` | your Gmail address |
| `SMTP_PASS` | the 16-char app password |
| `MAIL_TO` | where to send updates (comma-separate for several) |
| `SMTP_HOST` | *(optional)* defaults to `smtp.gmail.com` |
| `SMTP_PORT` | *(optional)* defaults to `587` |
| `MAIL_FROM` | *(optional)* defaults to `SMTP_USER` |

Using a different provider? Set `SMTP_HOST` / `SMTP_PORT` accordingly (e.g.
Outlook: `smtp.office365.com` / `587`).

Skip this section entirely and the timeline still updates — it just won't email.

### 4. If the source repo is **private**

Add a secret `SOURCE_REPO_TOKEN` — a
[fine-grained PAT](https://github.com/settings/tokens?type=beta) with **read access
to commits** on `rutejobs-mj-bladehandling-collab`. Public repos need no token.

### 5. Turn on Pages

Settings → Pages → Source: **Deploy from a branch** → Branch: `main` → `/ (root)`.
Your timeline will be at `https://<owner>.github.io/mj-bladehandling-commit-timeline/`.

### 6. First run

Actions tab → **Monitor commit timeline** → **Run workflow**. That populates
`data/commits.json` immediately instead of waiting for the next 2-hour slot.

---

## Good to know

- **Schedule drift.** GitHub queues cron jobs and can delay them during busy
  periods, so 2h is approximate. Runs are exact enough for this purpose.
- **Inactivity pause.** GitHub disables scheduled workflows after **60 days** with
  no commits to the repo. This workflow commits data every time it finds new
  commits, which keeps it alive; if the source repo goes quiet for months, re-enable
  it from the Actions tab.
- **First email.** The first run treats *all* existing commits as "already known"
  only if `data/commits.json` was already populated. On a fresh repo the seed file
  is empty, so the first run will email the current batch — run it once manually so
  you know what to expect.
- **Rate limits.** Unauthenticated API calls are 60/hour — fine at a 2h cadence.
  `GITHUB_TOKEN` (used automatically) raises this substantially.
- **Local preview.** Open `index.html` directly and it shows sample data with a
  "Preview mode" banner. Served from Pages with real `data/commits.json`, it goes live.

## Tuning

- Change cadence: edit the `cron` in `monitor.yml` (e.g. `0 */6 * * *` for every 6h).
- Keep more/less history: set a `MAX_KEEP` repo Variable (default 300).

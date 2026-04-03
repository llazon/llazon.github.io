---
layout: post
title: "Auditing Your GitHub Organization's Security Posture"
date: 2025-05-05
categories: security devops github
tags: github security audit permissions organizations compliance
---

# Auditing Your GitHub Organization's Security Posture

When was the last time you looked at who has access to what in your GitHub org? If you're like most teams, the answer is "not recently enough." People join, change roles, leave — and their access tends to only grow. I recently ran a full audit of our GitHub organization and want to share the approach and tooling.

## Why Audit?

- Former employees or contractors may still have access
- Repository permissions drift over time
- Outside collaborators accumulate without review
- Compliance frameworks (SOC 2, ISO 27001) require periodic access reviews
- You might be paying for seats you don't need

## The Audit Script

GitHub's REST API gives you everything you need. Here's the approach I used, broken into pieces:

### Pull Organization Members

```bash
#!/bin/bash
# Fetch all org members with their role

ORG="your-org-name"

gh api --paginate "/orgs/${ORG}/members?per_page=100" \
  --jq '.[] | {login: .login, id: .id, type: .type}' \
  > members.json

# Get member roles (admin vs member)
gh api --paginate "/orgs/${ORG}/members?role=admin&per_page=100" \
  --jq '.[].login' > admins.txt

echo "Total members: $(cat members.json | jq -s 'length')"
echo "Admins: $(wc -l < admins.txt)"
```

### Pull Outside Collaborators

These are the ones that tend to surprise people:

```bash
gh api --paginate "/orgs/${ORG}/outside_collaborators?per_page=100" \
  --jq '.[] | {login: .login, id: .id}' \
  > outside_collaborators.json

echo "Outside collaborators: $(cat outside_collaborators.json | jq -s 'length')"
```

### Pull Repository Permissions

```bash
# Get all repos
gh api --paginate "/orgs/${ORG}/repos?per_page=100&type=all" \
  --jq '.[] | {name: .name, private: .private, archived: .archived, default_branch_protection: .default_branch_protection}' \
  > repositories.json

# For each repo, get collaborators and their permission level
mkdir -p repos
while IFS= read -r repo; do
  gh api --paginate "/repos/${ORG}/${repo}/collaborators?per_page=100" \
    --jq '.[] | {login: .login, permissions: .permissions, role_name: .role_name}' \
    > "repos/${repo}.json" 2>/dev/null
done < <(jq -r '.name' repositories.json)
```

### Pull Team Structure

```bash
# Get all teams
gh api --paginate "/orgs/${ORG}/teams?per_page=100" \
  --jq '.[] | {name: .name, slug: .slug, permission: .permission, privacy: .privacy}' \
  > teams.json

# Get team members
mkdir -p teams
while IFS= read -r team_slug; do
  gh api --paginate "/orgs/${ORG}/teams/${team_slug}/members?per_page=100" \
    --jq '.[] | {login: .login}' \
    > "teams/${team_slug}.json" 2>/dev/null
done < <(jq -r '.slug' teams.json)
```

## Generating the Report

Once you have the raw data, generate a summary. Here's a Python script that produces CSV reports:

```python
import json
import csv
import os

def load_json_lines(filepath):
    items = []
    with open(filepath) as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items

def generate_user_access_summary():
    members = load_json_lines('members.json')
    admins = set()
    if os.path.exists('admins.txt'):
        with open('admins.txt') as f:
            admins = {line.strip() for line in f if line.strip()}

    with open('user_access_summary.csv', 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Username', 'Role', 'Repo Count', 'Team Count', 'Outside Collaborator'])

        for member in members:
            login = member['login']
            role = 'admin' if login in admins else 'member'

            # Count repos with direct access
            repo_count = 0
            for repo_file in os.listdir('repos'):
                collabs = load_json_lines(f'repos/{repo_file}')
                if any(c['login'] == login for c in collabs):
                    repo_count += 1

            # Count teams
            team_count = 0
            for team_file in os.listdir('teams'):
                team_members = load_json_lines(f'teams/{team_file}')
                if any(m['login'] == login for m in team_members):
                    team_count += 1

            writer.writerow([login, role, repo_count, team_count, 'No'])

    print("Generated user_access_summary.csv")

def generate_repo_summary():
    repos = load_json_lines('repositories.json')

    with open('repository_summary.csv', 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Repository', 'Private', 'Archived', 'Collaborator Count'])

        for repo in repos:
            repo_file = f"repos/{repo['name']}.json"
            collab_count = 0
            if os.path.exists(repo_file):
                collab_count = len(load_json_lines(repo_file))
            writer.writerow([repo['name'], repo['private'], repo['archived'], collab_count])

    print("Generated repository_summary.csv")

if __name__ == '__main__':
    generate_user_access_summary()
    generate_repo_summary()
```

## What to Look For

Once you have the data, here are the red flags:

1. **Org admins who shouldn't be** — admin access should be limited to a small group
2. **Outside collaborators on private repos** — review each one; do they still need access?
3. **Archived repos with active collaborators** — clean up access to archived repos
4. **Users with no team membership** — they might have direct repo access that bypasses your team structure
5. **Repos without branch protection** — especially on default branches
6. **Inactive users** — cross-reference with your HR/identity system

## Branch Protection Audit

While you're at it, check branch protection rules:

```bash
while IFS= read -r repo; do
  protection=$(gh api "/repos/${ORG}/${repo}/branches/main/protection" 2>/dev/null)
  if [ $? -ne 0 ]; then
    echo "UNPROTECTED: $repo"
  else
    reviews=$(echo "$protection" | jq '.required_pull_request_reviews.required_approving_review_count // 0')
    status_checks=$(echo "$protection" | jq '.required_status_checks != null')
    echo "PROTECTED: $repo (reviews: $reviews, status_checks: $status_checks)"
  fi
done < <(jq -r 'select(.archived == false) | .name' repositories.json)
```

## Automating the Audit

Run this quarterly at minimum. Set it up as a GitHub Action:

{% raw %}
```yaml
name: Quarterly Security Audit
on:
  schedule:
    - cron: '0 9 1 */3 *'  # First day of every quarter
  workflow_dispatch:

jobs:
  audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run audit
        env:
          GH_TOKEN: ${{ secrets.AUDIT_TOKEN }}
        run: |
          bash audit.sh
          python3 generate_report.py
      - name: Upload results
        uses: actions/upload-artifact@v4
        with:
          name: audit-report-${{ github.run_id }}
          path: |
            *.csv
            *.json
```
{% endraw %}

## Remediation Checklist

After the audit, work through this:

- [ ] Remove access for anyone who has left the organization
- [ ] Downgrade unnecessary admin accounts to member
- [ ] Remove outside collaborators who no longer need access
- [ ] Enable branch protection on all non-archived repos
- [ ] Require PR reviews on default branches
- [ ] Enable 2FA requirement for the organization
- [ ] Review and clean up deploy keys and personal access tokens
- [ ] Document the access review process for next time

## Tips

- Use the `gh` CLI instead of raw API calls — it handles pagination and auth cleanly
- Store audit results in a private repo for historical comparison
- Cross-reference GitHub users with your identity provider (Okta, Azure AD, etc.)
- Consider GitHub's built-in audit log for tracking changes between reviews
- If you're on GitHub Enterprise, the audit log API gives you even more detail

Regular access reviews aren't glamorous, but they're one of the most impactful security practices you can implement. An hour of auditing can close access gaps that have been open for months.

---

**References:**
- [GitHub REST API - Organizations](https://docs.github.com/en/rest/orgs)
- [GitHub Branch Protection](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-a-branch-protection-rule)
- [GitHub CLI](https://cli.github.com/)

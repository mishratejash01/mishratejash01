#!/usr/bin/env python3
"""Refresh the gh-ascii profile cards with real GitHub data.

The gh.crafter.run generator only sees public repos (and its commit/star counts
are unreliable), so we re-download the art and overwrite the stat values with
figures pulled live from the GitHub API via `gh`.

Usage:  ./update_card.py          (requires an authenticated `gh` CLI)
"""
import json
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone

USER = "mishratejash01"
CARDS = {"dark_mode.svg": "dark", "light_mode.svg": "light"}


def gh(args):
    out = subprocess.run(["gh", *args], capture_output=True, text=True)
    if out.returncode:
        sys.exit(f"gh {' '.join(args)} failed:\n{out.stderr}")
    return json.loads(out.stdout)


def collect():
    """Pull real profile + repo + lifetime-contribution numbers."""
    prof = gh(["api", "user"])
    created = datetime.strptime(prof["created_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)

    repos, cursor = [], None
    while True:
        page = gh(["api", "graphql", "-F", f"cursor={cursor}" if cursor else "cursor=", "-f", """query=
        query($cursor: String) {
          viewer { repositories(first: 100, ownerAffiliations: OWNER, after: $cursor) {
            pageInfo { hasNextPage endCursor }
            nodes { isPrivate stargazerCount primaryLanguage { name } } } }
        }"""])["data"]["viewer"]["repositories"]
        repos += page["nodes"]
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]

    # contributionsCollection caps at a 1-year window, so walk year by year.
    commits, year = 0, created.year
    now = datetime.now(timezone.utc)
    while year <= now.year:
        lo = max(created, datetime(year, 1, 1, tzinfo=timezone.utc))
        hi = min(now, datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc))
        c = gh(["api", "graphql",
                "-F", f"from={lo:%Y-%m-%dT%H:%M:%SZ}", "-F", f"to={hi:%Y-%m-%dT%H:%M:%SZ}",
                "-f", """query=
                query($from: DateTime!, $to: DateTime!) {
                  viewer { contributionsCollection(from: $from, to: $to) {
                    totalCommitContributions restrictedContributionsCount } }
                }"""])["data"]["viewer"]["contributionsCollection"]
        commits += c["totalCommitContributions"] + c["restrictedContributionsCount"]
        year += 1

    langs = {}
    for r in repos:
        if r["primaryLanguage"]:
            langs[r["primaryLanguage"]["name"]] = langs.get(r["primaryLanguage"]["name"], 0) + 1
    top = sorted(langs, key=lambda k: (-langs[k], k))[:3]

    days = (now - created).days
    y, rem = divmod(days, 365)
    m, d = divmod(rem, 30)
    uptime = ", ".join(f"{n} {u}{'s' * (n != 1)}" for n, u in ((y, "year"), (m, "month"), (d, "day")) if n)

    return {
        ". Uptime: ":    uptime,
        ". Company: ":   prof.get("company") or "-",
        ". Languages: ": ", ".join(top),
        ". Repos: ":     f"{len(repos):,}",
        ". Stars: ":     f"{sum(r['stargazerCount'] for r in repos):,}",
        ". Commits: ":   f"{commits:,}",
        ". Followers: ": f"{prof['followers']:,}",
    }


def patch(svg, values):
    """Rewrite each label/dots/value triple, keeping the monospace columns aligned."""
    pat = re.compile(
        r'(<tspan fill="[^"]*">)(\. [A-Za-z]+: )(</tspan><tspan fill="[^"]*">)(\.+)'
        r'(</tspan><tspan fill="[^"]*">) ([^<]*)(</tspan>)'
    )

    def sub(m):
        head, label, mid, dots, tail, old, end = m.groups()
        if label not in values:
            return m.group(0)
        new = values[label]
        width = len(label) + len(dots) + 1 + len(old)   # preserve total column width
        pad = width - len(label) - 1 - len(new)
        if pad < 1:                                      # value outgrew its slot
            pad = 1
        return f"{head}{label}{mid}{'.' * pad}{tail} {new}{end}"

    out, n = pat.subn(sub, svg)
    return out, n


def main():
    values = collect()
    print("Real data from the GitHub API:")
    for k, v in values.items():
        print(f"  {k.strip():<12} {v}")
    print()
    for fname, theme in CARDS.items():
        url = f"https://gh.crafter.run/{USER}?theme={theme}"
        with urllib.request.urlopen(url, timeout=30) as r:
            svg = r.read().decode()
        svg, n = patch(svg, values)
        open(fname, "w", encoding="utf-8").write(svg)
        print(f"  wrote {fname} ({n} fields corrected)")


if __name__ == "__main__":
    main()

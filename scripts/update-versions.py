#!/usr/bin/env python3
"""UCLI Registry version updater (gated).

Modes:
  --tool NAME   re-pin only NAME to its main tip (repository_dispatch).
                NAME may be "repo", "owner/repo" or a github.com URL.
  (no --tool)   daily run: re-pin a tool only when its new main commit has
                check runs and all of them are green (tools whose only
                check is the registry trigger job are pinned, labelled untested). Red, pending or
                unchecked commits are NOT pinned and are listed for review.

Options:
  --payload-file F   read the dispatch client_payload JSON from F and take the
                     tool from "name", else "tool" (the old payload, which
                     already carries owner/repo). An empty or tool-less payload
                     falls back to the daily all-green rule.
  --pr-body F        write a markdown PR body listing every decision to F
  --changed F        write the names of re-pinned tools, one per line, to F
  --pending-from REF read the open PR branch (e.g. origin/automated/version-updates)
                     and carry its still-pending pins over (see RegistryUpdater.carry_over)
  --dry-run, --verbose
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import index_tsv  # noqa: E402

GREEN = {"success", "neutral", "skipped"}


def gh_api(path: str):
    """Call `gh api` and return parsed JSON (None on failure). Mocked in tests."""
    r = subprocess.run(["gh", "api", path], capture_output=True, text=True)
    if r.returncode != 0:
        print(f"[ERROR] gh api {path}: {r.stderr.strip()}", file=sys.stderr)
        return None
    return json.loads(r.stdout)


def git_out(*args: str) -> Optional[str]:
    """Run git, return stdout or None on failure. Mocked in tests."""
    r = subprocess.run(["git", *args], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def owner_repo(repo_url: str) -> Optional[Tuple[str, str]]:
    m = re.match(r"(?:https?://)?github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$", repo_url)
    return m.groups() if m else None


def normalize_tool(value: Optional[str]) -> Optional[str]:
    """'ucli-tools/docx2md', 'github.com/x/docx2md' or 'docx2md' -> 'docx2md'."""
    if not value or not isinstance(value, str):
        return None
    value = value.strip().rstrip("/")
    if value.endswith(".git"):
        value = value[:-4]
    value = value.split("/")[-1]
    return value or None


def tool_from_payload(payload: Optional[Dict]) -> Optional[str]:
    if not isinstance(payload, dict):
        return None
    return normalize_tool(payload.get("name")) or normalize_tool(payload.get("tool"))


def is_on_main(repo_url: str, sha: str, default_branch: str = "main") -> bool:
    """True when sha is the tip of main or an ancestor of it."""
    o, r = owner_repo(repo_url)
    data = gh_api(f"repos/{o}/{r}/compare/{sha}...{default_branch}")
    return bool(data) and data.get("status") in ("identical", "ahead")


def latest_commit(repo_url: str, sha: Optional[str] = None) -> Optional[Dict]:
    pr = owner_repo(repo_url)
    if not pr:
        print(f"[ERROR] Invalid GitHub URL format: {repo_url}", file=sys.stderr)
        return None
    o, r = pr
    if sha:
        data = gh_api(f"repos/{o}/{r}/commits/{sha}")
        data = [data] if data else None
    else:
        data = gh_api(f"repos/{o}/{r}/commits?per_page=1")
    if not data:
        return None
    c = data[0]
    sha = c["sha"]
    d = datetime.fromisoformat(c["commit"]["committer"]["date"].replace("Z", "+00:00"))
    return {
        "hash": sha,
        "short_hash": sha[:8],
        "date": d.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "message": c["commit"]["message"].split("\n")[0],
        "url": f"https://github.com/{o}/{r}/commit/{sha}",
    }


def is_trigger(name: str) -> bool:
    return name.startswith("Trigger registry update")


def check_status(repo_url: str, sha: str) -> Tuple[str, str]:
    """Return (state, detail); state in green|untested|red|pending|unchecked|unknown."""
    pr = owner_repo(repo_url)
    if not pr:
        return "unknown", "bad repo URL"
    o, r = pr
    data = gh_api(f"repos/{o}/{r}/commits/{sha}/check-runs")
    if data is None:
        return "unknown", "check-runs query failed"
    runs = data.get("check_runs", [])
    if not runs:
        return "unchecked", "no check runs"
    bad = [c["name"] for c in runs if c.get("status") == "completed" and c.get("conclusion") not in GREEN]
    if bad:
        return "red", "failing: " + ", ".join(bad)
    waiting = [c["name"] for c in runs if c.get("status") != "completed"]
    if waiting:
        return "pending", "not finished: " + ", ".join(waiting)
    if any("(untested)" in c["name"] for c in runs):
        return "untested", f"{len(runs)} check run(s) green, but the tool has no tests"
    real = [c for c in runs if not is_trigger(c["name"]) and c.get("conclusion") == "success"]
    if not real:
        return "untested", "only the registry trigger job ran (no tests)"
    return "green", f"{len(runs)} check run(s) green"


class RegistryUpdater:
    def __init__(self, dry_run=False, verbose=False, tool=None, registry_file=None,
                 sha=None, tested=None, pending_from=None):
        self.pending_from = pending_from
        self.main_pins: Dict[str, str] = {}
        self.carried: Dict[str, Dict] = {}
        self.sha = sha if (sha and re.fullmatch(r"[0-9a-f]{40}", sha)) else None
        self.tested = tested
        self.dry_run = dry_run
        self.verbose = verbose
        self.tool = normalize_tool(tool)
        self.registry_file = Path(registry_file) if registry_file else (
            Path(__file__).parent.parent / "registry" / "apps.yaml")
        self.decisions: List[Dict] = []

    def error(self, message: str) -> None:
        print(f"[ERROR] {message}", file=sys.stderr)

    def load_registry(self) -> Optional[Dict]:
        try:
            with open(self.registry_file, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            self.error(f"Registry file not found: {self.registry_file}")
        except yaml.YAMLError as e:
            self.error(f"Error parsing YAML: {e}")
        return None

    def save_registry(self, registry: Dict) -> bool:
        try:
            registry["metadata"]["last_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            if not self.dry_run:
                with open(self.registry_file, "w", encoding="utf-8") as f:
                    yaml.safe_dump(registry, f, default_flow_style=False, sort_keys=False,
                                   allow_unicode=True, indent=2)
                (self.registry_file.parent / "index.tsv").write_text(
                    index_tsv.render(registry), encoding="utf-8")
            return True
        except Exception as e:
            self.error(f"Error saving registry: {e}")
            return False

    def decide(self, app: Dict) -> Dict:
        """Decide for one app; mutate it when the pin should change."""
        name = app.get("name", "unknown")
        repo = app.get("repo", "")
        old = app.get("version", "")
        d = {"name": name, "old": old, "new": old, "action": "kept", "status": "n/a", "note": ""}
        if not repo:
            d["note"] = "no repository URL"
            return d
        use_sha = self.sha if self.tool else None
        info = latest_commit(repo, use_sha)
        if not info:
            d["note"] = "could not fetch commit" + (f" {use_sha[:8]}" if use_sha else "")
            return d
        if use_sha and not is_on_main(repo, use_sha):
            d["status"] = "off-main"
            d["note"] = f"{use_sha[:8]} is not the main tip or an ancestor of it"
            return d
        d["new"] = info["hash"]
        if info["hash"] == old:
            d["note"] = "already at latest"
            d["new"] = old
            return d
        state, detail = check_status(repo, info["hash"])
        if self.tool and self.tested is False:
            state, detail = "untested", "tool sent tested:false (" + detail + ")"
        d["status"] = state
        d["note"] = f"{info['short_hash']}: {info['message'][:60]}; {detail}"
        # A named dispatch is gated by the tool's own tests (slice 4); the daily run
        # pins only all-green commits; untested ones (trigger job only) are pinned and labelled.
        if self.tool is None and state not in ("green", "untested"):
            d["action"] = "needs review"
            d["new"] = info["hash"]
            return d
        app["version"] = info["hash"]
        app.setdefault("version_info", {}).update({
            "commit_date": info["date"],
            "commit_message": info["message"],
            "commit_url": info["url"],
            "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        })
        d["action"] = "re-pinned"
        return d

    def carry_over(self, apps: List[Dict]) -> None:
        """Keep every pin change that is still pending on the PR branch.

        The PR branch is rebuilt from main on every run, so without this a later
        run (e.g. a named dispatch) would erase the pins an earlier run proposed.
        Approach: main is checked out; the PR branch's apps.yaml is read with
        `git show`, and its merge-base with main gives the pins the branch started
        from. A branch pin is PENDING when it differs from that base (the branch
        changed it) and from main (not merged yet). If main's pin differs from the
        base, a human edited it on main, and main wins. Only version and
        version_info are carried; the normal logic then runs on top, so a named
        tool or the daily rules replace their own older pending pin.
        """
        for a in apps:
            self.main_pins[a.get("name")] = a.get("version", "")
        if not self.pending_from:
            return
        theirs = git_out("show", f"{self.pending_from}:registry/apps.yaml")
        if not theirs:
            return
        mb = (git_out("merge-base", "HEAD", self.pending_from) or "").strip()
        base_text = git_out("show", f"{mb}:registry/apps.yaml") if mb else None
        try:
            branch_apps = yaml.safe_load(theirs)["apps"]["official"]
            base_apps = yaml.safe_load(base_text)["apps"]["official"] if base_text else []
        except (yaml.YAMLError, KeyError, TypeError):
            self.error("could not parse the PR branch registry; nothing carried over")
            return
        base_pins = {a.get("name"): a.get("version") for a in base_apps}
        by_name = {a.get("name"): a for a in apps}
        for b in branch_apps:
            name, ver = b.get("name"), b.get("version")
            cur = by_name.get(name)
            if cur is None or not ver or ver == cur.get("version"):
                continue  # unknown tool, or already merged to main
            base = base_pins.get(name, cur.get("version"))
            if cur.get("version") != base:
                continue  # a human changed it on main: main wins
            if ver == base:
                continue  # the branch did not change it
            cur["version"] = ver
            if b.get("version_info"):
                cur["version_info"] = b["version_info"]
            self.carried[name] = {"pin": ver}

    def run(self) -> bool:
        registry = self.load_registry()
        if not registry:
            return False
        apps = registry.get("apps", {}).get("official", [])
        if not apps:
            self.error("No official apps found in registry")
            return False
        self.carry_over(apps)
        targets = apps
        if self.tool:
            targets = [a for a in apps if a.get("name") == self.tool]
            if not targets:
                self.decisions.append({"name": self.tool, "old": "", "new": "", "action": "kept",
                                       "status": "n/a", "note": "not an official tool in the registry"})
        done = set()
        for app in targets:
            name = app.get("name")
            d = self.decide(app)
            if name in self.carried:
                if d["action"] == "re-pinned":
                    pass  # this run supersedes the older pending pin
                else:
                    # keep the carried pin; its status is refreshed below
                    if d["action"] == "needs review":
                        self.carried[name]["extra"] = f"newer tip not pinned ({d['status']}): {d['note']}"
                    d = None
            if d:
                if d["action"] == "re-pinned":
                    d["old"] = self.main_pins.get(name, d["old"])
                    self.carried.pop(name, None)
                self.decisions.append(d)
                print(f"{name}: {d['action']} ({d['status']}) {d['note']}")
        # Carried pins this run did not touch: refresh status so a pin whose checks
        # have finished shows its final green or red, not an old "pending".
        for app in apps:
            name = app.get("name")
            if name not in self.carried:
                continue
            c = self.carried[name]
            state, detail = check_status(app.get("repo", ""), c["pin"])
            note = f"{c['pin'][:8]}: {detail}" + (f"; {c['extra']}" if c.get("extra") else "")
            self.decisions.append({"name": name, "old": self.main_pins.get(name, ""), "new": c["pin"],
                                   "action": "carried", "status": state, "note": note})
            print(f"{name}: carried ({state}) {note}")
        if any(d["action"] in ("re-pinned", "carried") for d in self.decisions):
            if not self.save_registry(registry):
                return False
        else:
            print("No pin changes")
        return True

    def changed(self) -> List[str]:
        return [d["name"] for d in self.decisions if d["action"] in ("re-pinned", "carried")]

    def pr_body(self) -> str:
        mode = f"dispatch for `{self.tool}`" if self.tool else "daily run (green and untested commits; red, pending, unchecked kept)"
        lines = ["## Tool pin update", "", f"Trigger: {mode}.", "",
                 "| Tool | Old pin | New pin | Check status | Action |", "|---|---|---|---|---|"]
        for d in self.decisions:
            if d["action"] == "kept" and not d["note"].startswith("not an official"):
                continue
            lines.append(f"| {d['name']} | `{d['old'][:8]}` | `{d['new'][:8]}` | {d['status']} | {d['action']} |")
        flagged = [d for d in self.decisions if d["status"] in ("red", "unchecked", "pending", "unknown", "untested", "off-main")]
        if flagged:
            lines += ["", "### Flagged: red, pending or unchecked commits", ""]
            for d in flagged:
                verb = {"re-pinned": "pinned anyway (named dispatch)",
                        "carried": "pinned in this PR"}.get(d["action"], "NOT pinned, needs review")
                lines.append(f"- **{d['name']}** ({d['status']}): {d['note']} - {verb}")
        lines += ["", "Validated by `validate.py`, the unit tests and `make -n build` on every new pin before this PR was opened. Merge is by the operator."]
        return "\n".join(lines) + "\n"


def main():
    p = argparse.ArgumentParser(description="Update UCLI Registry pins (gated)")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--verbose", "-v", action="store_true")
    p.add_argument("--tool")
    p.add_argument("--payload-file")
    p.add_argument("--pr-body")
    p.add_argument("--changed")
    p.add_argument("--pending-from")
    a = p.parse_args()

    tool = a.tool
    sha = tested = None
    if not tool and a.payload_file and Path(a.payload_file).is_file():
        try:
            pl = json.loads(Path(a.payload_file).read_text() or "null")
            tool = tool_from_payload(pl)
            if isinstance(pl, dict):
                sha = pl.get("sha")
                tested = pl.get("tested") if isinstance(pl.get("tested"), bool) else None
        except json.JSONDecodeError:
            tool = None
    u = RegistryUpdater(dry_run=a.dry_run, verbose=a.verbose, tool=tool, sha=sha, tested=tested,
                        pending_from=a.pending_from)
    ok = u.run()
    if a.pr_body:
        Path(a.pr_body).write_text(u.pr_body())
    if a.changed:
        Path(a.changed).write_text("".join(n + "\n" for n in u.changed()))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

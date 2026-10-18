import importlib.util
import sys
import unittest
from pathlib import Path
from unittest import mock

import yaml

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("uv", ROOT / "scripts" / "update-versions.py")
uv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(uv)

OLD = "a" * 40
NEW = {"aaa": "b" * 40, "bbb": "c" * 40, "ccc": "d" * 40}
CHECKS = {}


def fake_gh(path):
    parts = path.split("/")
    repo = parts[2]
    if "/commits?" in path:
        sha = NEW[repo]
        return [{"sha": sha, "commit": {"message": f"change {repo}", "committer": {"date": "2026-10-17T00:00:00Z"}}}]
    if path.endswith("/check-runs"):
        return {"check_runs": CHECKS.get(repo, [])}
    raise AssertionError(path)


def run(c, s="completed"):
    return {"name": "t", "status": s, "conclusion": c}


class Base(unittest.TestCase):
    def setUp(self):
        self.reg = ROOT / "tests" / "_fixture_apps.yaml"
        apps = [{"name": n, "repo": f"github.com/o/{n}", "version": OLD} for n in NEW]
        self.reg.write_text(yaml.safe_dump({"metadata": {}, "apps": {"official": apps}}))
        self.addCleanup(self.reg.unlink)
        CHECKS.clear()
        p = mock.patch.object(uv, "gh_api", fake_gh)
        p.start()
        self.addCleanup(p.stop)

    def upd(self, tool=None):
        u = uv.RegistryUpdater(tool=tool, registry_file=self.reg)
        self.assertTrue(u.run())
        return u

    def pins(self):
        return {a["name"]: a["version"] for a in yaml.safe_load(self.reg.read_text())["apps"]["official"]}


class Tests(Base):
    def test_single_tool_dispatch_only_touches_that_tool(self):
        u = self.upd(tool="bbb")
        self.assertEqual(u.changed(), ["bbb"])
        self.assertEqual(self.pins(), {"aaa": OLD, "bbb": NEW["bbb"], "ccc": OLD})

    def test_payload_forms(self):
        self.assertEqual(uv.tool_from_payload({"tool": "ucli-tools/docx2md"}), "docx2md")
        self.assertEqual(uv.tool_from_payload({"tool": "ucli-tools/x", "name": "docx2md", "sha": "1"}), "docx2md")
        self.assertIsNone(uv.tool_from_payload({}))
        self.assertIsNone(uv.tool_from_payload(None))

    def test_old_payload_tool_is_used(self):
        u = self.upd(tool=uv.tool_from_payload({"tool": "o/ccc"}))
        self.assertEqual(u.changed(), ["ccc"])

    def test_daily_all_green_pins_all(self):
        for n in NEW:
            CHECKS[n] = [run("success"), run("skipped")]
        u = self.upd()
        self.assertEqual(sorted(u.changed()), sorted(NEW))
        self.assertEqual(self.pins(), NEW)

    def test_daily_red_and_unchecked_kept(self):
        CHECKS["aaa"] = [run("success")]
        CHECKS["bbb"] = [run("success"), run("failure")]
        CHECKS["ccc"] = []
        u = self.upd()
        self.assertEqual(u.changed(), ["aaa"])
        self.assertEqual(self.pins(), {"aaa": NEW["aaa"], "bbb": OLD, "ccc": OLD})

    def test_daily_pending_kept(self):
        CHECKS["aaa"] = [run(None, "in_progress")]
        self.assertEqual(self.upd().changed(), [])

    def test_pr_body_lists_flags(self):
        CHECKS["aaa"] = [run("success")]
        CHECKS["bbb"] = [run("failure")]
        body = self.upd().pr_body()
        self.assertIn("| aaa |", body)
        self.assertIn("green", body)
        self.assertIn("**bbb** (red)", body)
        self.assertIn("NOT pinned", body)
        self.assertIn("**ccc** (unchecked)", body)

    def test_unknown_tool_changes_nothing(self):
        u = self.upd(tool="zzz")
        self.assertEqual(u.changed(), [])
        self.assertEqual(self.pins(), {n: OLD for n in NEW})

    def test_named_dispatch_flags_unchecked_but_pins(self):
        body = self.upd(tool="ccc").pr_body()
        self.assertIn("pinned anyway", body)


if __name__ == "__main__":
    unittest.main()

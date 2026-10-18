import importlib.util
import sys
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import index_tsv  # noqa: E402

spec = importlib.util.spec_from_file_location("validate", ROOT / "scripts" / "validate.py")
validate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validate)

SHA = "a" * 40
DATA = {"apps": {
    "official": [
        {"name": "x", "repo": "github.com/o/x", "version": SHA, "pattern": "cli"},
        {"name": "y", "repo": "github.com/o/y", "version": "b" * 40, "pattern": "cli"},
    ],
    "community": [{"name": "c", "repo": "github.com/o/c", "version": SHA, "pattern": "cli"}],
    "templates": [{"name": "t", "repo": "github.com/o/t", "version": SHA, "pattern": "cli"}],
}}


class IndexTsv(unittest.TestCase):
    def test_render_official_only_with_header(self):
        self.assertEqual(
            index_tsv.render(DATA),
            "#name\trepo\tcommit\tkind\n"
            f"x\tgithub.com/o/x\t{SHA}\tcli\n"
            f"y\tgithub.com/o/y\t{'b' * 40}\tcli\n")

    def test_committed_index_matches_committed_registry(self):
        reg = ROOT / "registry"
        data = yaml.safe_load((reg / "apps.yaml").read_text())
        self.assertEqual((reg / "index.tsv").read_text(), index_tsv.render(data))
        self.assertEqual(len(data["apps"]["official"]),
                         len((reg / "index.tsv").read_text().splitlines()) - 1)

    def _check(self, content):
        p = ROOT / "tests" / "_fixture_index.tsv"
        if content is not None:
            p.write_text(content)
        self.addCleanup(p.unlink, missing_ok=True)
        return validate.check_index(DATA, p)

    def test_agreement_passes(self):
        self.assertEqual(self._check(index_tsv.render(DATA)), [])

    def test_hand_edited_pin_fails(self):
        stale = index_tsv.render(DATA).replace(SHA, "c" * 40)
        self.assertEqual(len(self._check(stale)), 1)

    def test_missing_index_fails(self):
        (ROOT / "tests" / "_fixture_index.tsv").unlink(missing_ok=True)
        self.assertEqual(len(self._check(None)), 1)

    def test_updater_writes_index_with_pin_change(self):
        # covered end to end in test_update_versions; here: a pin change in data changes the render
        changed = yaml.safe_load(yaml.safe_dump(DATA))
        changed["apps"]["official"][0]["version"] = "d" * 40
        self.assertNotEqual(index_tsv.render(changed), index_tsv.render(DATA))


if __name__ == "__main__":
    unittest.main()

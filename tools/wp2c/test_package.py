import importlib.util
from hashlib import sha256
from pathlib import Path
import tempfile
import unittest

class PackagingTests(unittest.TestCase):
    def test_self_contained_hashed_build_and_no_source_mutation(self):
        from tools.wp2c.package import build
        with tempfile.TemporaryDirectory(prefix="heating-wp2c-package-") as target:
            report=build(Path(target))
            root=Path(target)/"custom_components/heating_ai"
            self.assertTrue((root/"core/ha_native/fixture.json").is_file())
            self.assertTrue((root/"assets/panel.js").is_file())
            self.assertGreater(len(report["files"]),35)
            for item in report["files"]:
                self.assertEqual(sha256((Path(target)/item["artifact"]).read_bytes()).hexdigest(), item["sha256"])
                self.assertEqual(sha256(Path(item["source"]).read_bytes()).hexdigest(), item["source_sha256"])
            code=(root/"core/ha_native/backend.py").read_text()
            self.assertNotIn("from packages.",code)

    def test_refuses_non_disposable_or_nonempty_targets(self):
        from tools.wp2c.package import build
        with self.assertRaises(ValueError):
            build(Path.cwd())
        with tempfile.TemporaryDirectory(prefix="heating-wp2c-package-") as target:
            (Path(target)/"existing").write_text("do not overwrite")
            with self.assertRaises(ValueError):
                build(Path(target))

    def test_refuses_linked_destination_without_writing_target(self):
        from tools.wp2c.package import build
        with tempfile.TemporaryDirectory(prefix="heating-wp2c-package-") as target:
            link=Path(target).with_name(Path(target).name+"-link")
            try:
                link.symlink_to(target, target_is_directory=True)
                with self.assertRaises(ValueError):
                    build(link)
                self.assertEqual(list(Path(target).iterdir()), [])
            finally:
                link.unlink(missing_ok=True)

if __name__=="__main__":
    unittest.main()

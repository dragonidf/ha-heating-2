"""Real Playwright output cleanup against read-only source, without HA or a browser."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class BrowserOutputTests(unittest.TestCase):
    def test_reporters_preserve_mountpoint_directories_under_read_only_source(self):
        self.assertNotEqual(os.geteuid(), 0, "Run filesystem qualification as the unprivileged runner")
        with tempfile.TemporaryDirectory(prefix="wp2c-outputs-") as temporary:
            root = Path(temporary)
            (root / "tests").mkdir()
            (root / "node_modules").symlink_to(ROOT / "frontend/node_modules", target_is_directory=True)
            (root / "tests/output.spec.ts").write_text(
                'import {test} from "@playwright/test"; import {writeFileSync} from "node:fs";'
                'test("writes artifacts without removing mountpoints", ({}, info) => {'
                'writeFileSync(info.outputPath("proof.txt"), "synthetic output only");});'
            )
            config = json.dumps(str(ROOT / "frontend/playwright.native.config.ts"))
            (root / "playwright.config.ts").write_text(
                f'import config from {config}; export default {{...config, testDir:"./tests"}};'
            )
            for directory in ("test-results", "playwright-report-native"):
                (root / directory).mkdir(mode=0o777)
            root.chmod(0o555)
            try:
                result = subprocess.run(
                    ["node", str(ROOT / "frontend/node_modules/@playwright/test/cli.js"),
                     "test", "--config", str(root / "playwright.config.ts")],
                    cwd=root, capture_output=True, text=True, timeout=40,
                )
                self.assertEqual(result.returncode, 0, (result.stdout + result.stderr)[-5000:])
                report = json.loads((root / "test-results/native-results.json").read_text())
                self.assertEqual(report["stats"]["expected"], 4)
                self.assertEqual(report["stats"]["skipped"], 0)
                self.assertEqual(report["stats"]["unexpected"], 0)
                self.assertTrue((root / "test-results/native-artifacts").is_dir())
                self.assertTrue((root / "playwright-report-native/report/index.html").is_file())
            finally:
                root.chmod(0o700)


if __name__ == "__main__":
    unittest.main()

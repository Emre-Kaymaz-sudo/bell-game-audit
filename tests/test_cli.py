"""Exercise the public command and the isolated verification path printed in the PDF."""

import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[1]


class VerificationCommandTests(unittest.TestCase):
    def test_package_and_isolated_verifier_agree_without_site_packages(self):
        inputs = ["result.json", "private_certificate.json"]
        commands = [
            ["-S", "-m", "bell_game_audit", "verify-certificate"],
            ["-I", "-S", "verify_private_certificate.py"],
        ]
        reports = [
            json.loads(subprocess.check_output([sys.executable, *args, *inputs], cwd=ROOT))
            for args in commands
        ]
        self.assertEqual(reports[0], reports[1])
        self.assertEqual((reports[0]["lower"], reports[0]["upper"]), ("22/27", "22/27"))

    def test_subcommand_is_named_in_usage_errors(self):
        result = subprocess.run(
            [sys.executable, "-S", "-m", "bell_game_audit", "verify-result"],
            cwd=ROOT, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("usage: bell-game-audit verify-result", result.stderr)

    def test_audit_build_controls_and_replay_reject_the_same_ambiguous_game(self):
        with TemporaryDirectory() as folder:
            ambiguous = Path(folder) / "result.json"
            ambiguous.write_text('{"winner": {}, "winner": {}}', encoding="utf-8-sig")
            for command in ("audit", "build-certificate", "controls", "replay"):
                with self.subTest(command=command):
                    args = [command, str(ambiguous)]
                    if command == "replay":
                        args.append(str(Path(folder) / "unused.bin"))
                    result = subprocess.run(
                        [sys.executable, "-m", "bell_game_audit", *args],
                        cwd=ROOT, capture_output=True, text=True,
                    )
                    self.assertEqual(result.returncode, 2)
                    self.assertIn("duplicate JSON field 'winner'", result.stderr)
                    self.assertNotIn("Traceback", result.stderr)

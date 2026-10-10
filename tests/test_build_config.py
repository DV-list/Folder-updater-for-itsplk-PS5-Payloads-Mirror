"""Guardrails for the optimized PyInstaller command and CustomTkinter runtime."""
import unittest
from pathlib import Path


class BuildConfigTests(unittest.TestCase):
    def test_build_keeps_customtkinter_and_size_optimizations(self):
        root = Path(__file__).resolve().parents[1]
        command = (root / "build.txt").read_text(encoding="utf-8")
        requirements = (root / "requirements.txt").read_text(encoding="utf-8").lower()
        self.assertIn("--optimize 2", command)
        self.assertIn("--collect-data customtkinter", command)
        self.assertIn("--hidden-import customtkinter", command)
        self.assertIn("--exclude-module unittest", command)
        self.assertIn("--exclude-module tkinter.test", command)
        self.assertIn("customtkinter", requirements)


if __name__ == "__main__":
    unittest.main()

"""
WAR ROOM — Test Ping: Full Stack
Runs all connectivity tests: Gemini API + GCP Firestore.
"""

import os
import sys
import subprocess

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def main():
    print("\n" + "=" * 55)
    print("  ⚔️  WAR ROOM — Full Connectivity Test Suite")
    print("=" * 55)

    scripts = [
        ("Gemini API", os.path.join(os.path.dirname(__file__), "test_ping_gemini.py")),
        ("GCP Firestore", os.path.join(os.path.dirname(__file__), "test_ping_gcp.py")),
    ]

    all_passed = True
    for name, script in scripts:
        print(f"\n{'─' * 55}")
        print(f"  Running: {name}")
        print(f"{'─' * 55}")
        result = subprocess.run(
            [sys.executable, script],
            cwd=os.path.join(os.path.dirname(__file__), ".."),
        )
        if result.returncode != 0:
            all_passed = False

    print(f"\n{'=' * 55}")
    if all_passed:
        print("  🎉 ALL CONNECTIVITY TESTS PASSED!")
    else:
        print("  ⚠️  Some tests had issues — review output above")
    print("=" * 55 + "\n")


if __name__ == "__main__":
    main()

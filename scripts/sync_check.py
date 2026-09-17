#!/usr/bin/env python3
"""
SkillOpt repo sync-check — monthly.

1. Fetch upstream microsoft/SkillOpt and merge origin/main into the local
   working branch (our integration lives on main with a small additive
   diff: skillopt/envs/pricewatch/, configs/pricewatch/, 2 registration
   lines in scripts/train.py and scripts/eval_only.py, plus the config.py
   env-section fix that is also upstreamed as PR #259).
2. If the merge is clean, reinstall the venv (editable) and run the
   regression + smoke tests:
     - tests/test_env_section_survives_dedup.py  (env-section fix)
     - tests/test_codex_config_aliases.py        (config dedup behavior)
     - eval_only on the pricewatch val split with the seed skill (backend
       smoke test; requires ARK credentials via HERMES_ARK_API_KEY)
3. Print a short status summary. The cron wrapper keeps this SILENT when
   everything is up to date and passing (no news = good news); it reports
   only on merge conflicts, failed tests, or stale branches.

Exit codes: 0 = clean & passing, 1 = failure (conflict/test/backend), 2 = no change needed.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path("/home/tom/workspaces/emma/skillopt-pricewatch")
UPSTREAM_URL = "https://github.com/microsoft/SkillOpt.git"
LOCAL_BRANCH = "main"

# Tests that must pass after a sync.
REQUIRED_TESTS = [
    "tests/test_env_section_survives_dedup.py",
    "tests/test_codex_config_aliases.py",
]


def run(cmd: list[str], cwd: Path, timeout: int = 600, check: bool = False,
        env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                          timeout=timeout, check=check, env=env)


def main() -> int:
    changes = []

    # 1. Fetch + merge upstream
    r = run(["git", "fetch", UPSTREAM_URL, "main"], REPO)
    if r.returncode != 0:
        print(f"❌ git fetch failed: {r.stderr[-400:]}")
        return 1

    r = run(["git", "rev-parse", "HEAD"], REPO)
    before = r.stdout.strip()
    r = run(["git", "rev-parse", "FETCH_HEAD"], REPO)
    upstream = r.stdout.strip()

    if before == upstream:
        changes.append("no upstream changes")
    else:
        changes.append(f"upstream moved: {before[:10]} -> {upstream[:10]}")
        r = run(["git", "merge", "--no-edit", "FETCH_HEAD"], REPO, timeout=300)
        if r.returncode != 0:
            print("❌ git merge conflict with upstream:")
            print(r.stdout[-2000:])
            print(r.stderr[-500:])
            return 1
        changes.append("merged cleanly")
        # Reinstall editable so any new deps/code are picked up.
        run([str(REPO / ".venv/bin/pip"), "install", "-q", "-e", "."], REPO, timeout=600)

    # 2. Run tests
    for t in REQUIRED_TESTS:
        r = run([str(REPO / ".venv/bin/python"), "-m", "pytest", t, "-q"], REPO, timeout=600)
        if r.returncode != 0:
            print(f"❌ pytest failed: {t}")
            print(r.stdout[-1500:])
            print(r.stderr[-500:])
            return 1
    changes.append("tests passed")

    # 3. Backend smoke test (eval on val split) — silent unless it fails
    env = dict(os.environ)
    env.update({
        "OPENAI_COMPATIBLE_BASE_URL": "https://ark.cn-beijing.volces.com/api/plan/v3",
        "OPENAI_COMPATIBLE_MODEL": "deepseek-v4-flash",
    })
    if not env.get("HERMES_ARK_API_KEY"):
        print("⚠️ HERMES_ARK_API_KEY not set — skipping backend smoke test (tests still passed).")
    else:
        env["OPENAI_COMPATIBLE_API_KEY"] = env["HERMES_ARK_API_KEY"]
        r = run(
            [str(REPO / ".venv/bin/python"), "scripts/eval_only.py",
             "--config", "configs/pricewatch/default.yaml",
             "--skill", "skillopt/envs/pricewatch/skills/initial.md",
             "--split", "val"],
            REPO, timeout=600, env=env,
        )
        if r.returncode != 0 or "hard=1.0000" not in r.stdout:
            print("❌ backend smoke eval failed (val split not 1.0000):")
            print(r.stdout[-1500:])
            print(r.stderr[-500:])
            return 1
        changes.append("backend smoke eval passed (val hard=1.0)")

    # 4. Report — only when something actually happened; silence otherwise
    if "no upstream changes" in changes:
        return 2  # no news = good news: stay silent (watchdog pattern)
    print("✅ SkillOpt sync OK — " + ", ".join(changes))
    return 0


if __name__ == "__main__":
    sys.exit(main())

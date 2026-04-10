"""Script temporaire pour commit+push (contournement problème terminal)."""
import subprocess, os
os.chdir(r"C:\Users\ilies\git\bitcoin-trading-assistant")

cmds = [
    ["git", "add", "-A"],
    ["git", "commit", "-m", "fix(scalping): expected_capture_pct 0.50 - deblocage gate economique + docs completes"],
    ["git", "push"],
]

for cmd in cmds:
    print(f"\n>>> {' '.join(cmd)}")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.stdout: print(r.stdout.strip())
    if r.stderr: print(r.stderr.strip())
    print(f"[exit code: {r.returncode}]")


import subprocess, os
os.chdir(r"C:\Users\ilies\git\bitcoin-trading-assistant")
cmds = [
    ["git", "add", "-A"],
    ["git", "commit", "-m", "docs(rules): ajout regles d'or n1 (docs completes) + n2 (HANDOFF_GPT.md) + mise a jour CLAUDE.md v1.1.0"],
    ["git", "push"],
]
for cmd in cmds:
    print(f"\n>>> {' '.join(cmd)}")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.stdout: print(r.stdout.strip())
    if r.stderr: print(r.stderr.strip())
    print(f"[exit code: {r.returncode}]")


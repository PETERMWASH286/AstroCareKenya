import sys
import subprocess

# Files/directories that must never be committed
FORBIDDEN = [".env", "venv", "migrations"]

# Get staged files
result = subprocess.run(["git", "diff", "--cached", "--name-only"], stdout=subprocess.PIPE)
staged_files = result.stdout.decode().splitlines()

blocked = False

for file in staged_files:
    for forbidden_file in FORBIDDEN:
        if file.startswith(forbidden_file):
            print(f"Error: Forbidden file detected: '{file}'")
            blocked = True

if blocked:
    print("Commit aborted. Remove forbidden files from staging first.")
    sys.exit(1)

sys.exit(0)

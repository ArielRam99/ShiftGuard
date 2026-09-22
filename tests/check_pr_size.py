"""Count changed production lines separately from tests and documentation."""
import subprocess
import sys


def production_line_count(base, head):
    output = subprocess.check_output(
        ["git", "diff", "--numstat", f"{base}...{head}"], text=True
    )
    production = 0
    excluded = 0
    for line in output.splitlines():
        added, removed, path = line.split("\t", 2)
        if added == "-" or removed == "-":
            raise ValueError(f"Binary change requires a separate review: {path}")
        count = int(added) + int(removed)
        if path.startswith(("tests/", "tests-js/", "docs/")) or path.endswith(".md"):
            excluded += count
        else:
            production += count
    return production, excluded


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Usage: check_pr_size.py BASE_SHA HEAD_SHA")
    production, excluded = production_line_count(*sys.argv[1:])
    print(f"Production: {production} changed lines; tests/docs: {excluded} separate lines")
    if production > 200:
        raise SystemExit("Focused PR exceeds the 200-production-line budget")

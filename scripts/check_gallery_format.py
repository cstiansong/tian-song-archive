import argparse
import re
import subprocess
import sys
from pathlib import Path


LEGACY_PATTERNS = [
    re.compile(r"<div\b", re.IGNORECASE),
    re.compile(r"<img[^>]*\bstyle=", re.IGNORECASE),
]

TABLE_IMAGE_LINE = re.compile(r"^\s*\|.*!\[[^\]]*\]\([^)]+\).*$")
UPDATED_FILES_LINE = re.compile(r"^- Updated files:\s*(\d+)\s*$", re.MULTILINE)


def _has_legacy_gallery_format(text: str) -> bool:
    for p in LEGACY_PATTERNS:
        if p.search(text):
            return True
    for line in text.splitlines():
        if TABLE_IMAGE_LINE.match(line):
            return True
    return False


def _check_legacy_blocks(docs_dir: Path) -> list[Path]:
    bad_files: list[Path] = []
    for md in sorted(docs_dir.rglob("*.md")):
        text = md.read_text(encoding="utf-8")
        if _has_legacy_gallery_format(text):
            bad_files.append(md)
    return bad_files


def _check_idempotent(docs_dir: Path) -> tuple[int, str]:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/auto_gallery_layout.py",
            "--path",
            str(docs_dir),
            "--dry-run",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return -1, result.stdout + "\n" + result.stderr

    m = UPDATED_FILES_LINE.search(result.stdout)
    if not m:
        return -1, result.stdout
    return int(m.group(1)), result.stdout


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fail when markdown gallery format is not normalized."
    )
    parser.add_argument("--docs", type=Path, default=Path("docs"), help="Docs directory")
    args = parser.parse_args()

    docs_dir = args.docs.resolve()
    if not docs_dir.exists() or not docs_dir.is_dir():
        raise FileNotFoundError(f"Docs directory not found: {docs_dir}")

    bad_files = _check_legacy_blocks(docs_dir)
    if bad_files:
        print("FAIL")
        print("- Legacy gallery format found:")
        for p in bad_files[:100]:
            print(f"  - {p}")
        if len(bad_files) > 100:
            print(f"  ... and {len(bad_files) - 100} more")
        print("- Run: python scripts/auto_gallery_layout.py --path docs")
        raise SystemExit(1)

    updated_files, output = _check_idempotent(docs_dir)
    if updated_files < 0:
        print("FAIL")
        print("- Could not parse dry-run output from auto_gallery_layout.py")
        print(output)
        raise SystemExit(1)
    if updated_files != 0:
        print("FAIL")
        print(f"- Gallery layout not normalized, updated_files={updated_files}")
        print(output)
        print("- Run: python scripts/auto_gallery_layout.py --path docs")
        raise SystemExit(1)

    print("OK")
    print("- Gallery format normalized")


if __name__ == "__main__":
    main()

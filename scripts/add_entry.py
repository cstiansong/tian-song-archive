import argparse
import os
import re
import urllib.parse
from pathlib import Path


SPECIAL_DIR_REL = Path("docs/松/松史/追求女生的经历")
SPECIAL_INDEX_REL = Path("docs/松/松史/index.md")
SPECIAL_HEADING = "# 追求女生的经历"


def _quote_path(path_str: str) -> str:
    return urllib.parse.quote(path_str, safe="/%._-~")


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _md_path(target_dir: Path, name: str) -> Path:
    return target_dir / f"{name}.md"


def _asset_dir(target_dir: Path, name: str) -> Path:
    return target_dir / name


def _ensure_entry_files(
    *, target_dir: Path, name: str, force: bool, dry_run: bool
) -> list[str]:
    actions: list[str] = []
    md = _md_path(target_dir, name)
    assets = _asset_dir(target_dir, name)

    if md.exists() and not force:
        raise FileExistsError(f"Entry already exists: {md}")

    if not dry_run:
        target_dir.mkdir(parents=True, exist_ok=True)

    if md.exists() and force:
        actions.append(f"overwrite: {md}")
    else:
        actions.append(f"create: {md}")

    if not dry_run:
        md.write_text(f"# {name}\n\n", encoding="utf-8")

    if assets.exists():
        actions.append(f"exists: {assets}")
    else:
        actions.append(f"create: {assets}")
        if not dry_run:
            assets.mkdir(parents=True, exist_ok=True)

    return actions


def _update_pages_file(*, target_dir: Path, name: str, dry_run: bool) -> str:
    pages = target_dir / ".pages"
    entry = f"{name}.md"
    if not pages.exists():
        return f"skip .pages (not found): {pages}"

    text = pages.read_text(encoding="utf-8")
    lines = text.splitlines()

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("- ") and stripped[2:].strip() == entry:
            return f"skip .pages (already has entry): {pages}"

    has_nav = any(line.strip() == "nav:" for line in lines)
    if not has_nav:
        if lines and lines[-1].strip() != "":
            lines.append("")
        lines.append("nav:")
    lines.append(f"  - {entry}")

    if not dry_run:
        pages.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return f"update .pages: {pages}"


def _is_same_dir(a: Path, b: Path) -> bool:
    return a.resolve() == b.resolve()


def _find_section_bounds(lines: list[str], heading: str) -> tuple[int, int] | None:
    start = -1
    for i, line in enumerate(lines):
        if line.strip() == heading:
            start = i
            break
    if start < 0:
        return None

    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].startswith("# "):
            end = i
            break
    return start, end


def _section_has_link(section_lines: list[str], name: str) -> bool:
    link_re = re.compile(r"\[(?P<label>[^\]]+)\]\((?P<target>[^)]+)\)")
    target_name = f"{name}.md"
    for line in section_lines:
        for m in link_re.finditer(line):
            label = m.group("label").strip()
            target = urllib.parse.unquote(m.group("target").strip())
            if label == name:
                return True
            if Path(target).name == target_name:
                return True
    return False


def _update_special_index(
    *, repo_root: Path, target_dir: Path, name: str, dry_run: bool
) -> str:
    special_dir = (repo_root / SPECIAL_DIR_REL).resolve()
    if not _is_same_dir(target_dir, special_dir):
        return "skip 松史 index update (non-special dir)"

    index_path = repo_root / SPECIAL_INDEX_REL
    if not index_path.exists():
        return f"skip 松史 index update (missing): {index_path}"

    lines = index_path.read_text(encoding="utf-8").splitlines()
    bounds = _find_section_bounds(lines, SPECIAL_HEADING)
    if bounds is None:
        return f"skip 松史 index update (heading not found): {SPECIAL_HEADING}"

    start, end = bounds
    section_lines = lines[start:end]
    if _section_has_link(section_lines, name):
        return f"skip 松史 index update (already has link): {index_path}"

    rel = Path(os.path.relpath(_md_path(target_dir, name), index_path.parent)).as_posix()
    encoded = _quote_path(rel)
    link_line = f"[{name}]({encoded})"

    insert_at = end
    while insert_at > start + 1 and lines[insert_at - 1].strip() == "":
        insert_at -= 1

    chunk: list[str] = []
    if insert_at > start + 1 and lines[insert_at - 1].strip() != "":
        chunk.append("")
    chunk.append(link_line)
    chunk.append("")

    new_lines = lines[:insert_at] + chunk + lines[insert_at:]
    if not dry_run:
        index_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    return f"update 松史 index: {index_path}"


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Create a new entry markdown + asset folder under a directory, "
            "then update .pages and related index links."
        )
    )
    parser.add_argument(
        "--dir",
        type=Path,
        required=True,
        help="Target directory for the new entry (e.g. docs/松/松史/追求女生的经历).",
    )
    parser.add_argument("--name", required=True, help="New entry name (without .md suffix).")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing markdown file if it already exists.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned changes without writing files.",
    )
    args = parser.parse_args()

    name = args.name.strip()
    if not name:
        raise ValueError("--name cannot be empty")
    if "/" in name or "\\" in name:
        raise ValueError("--name cannot contain path separators")

    target_dir = args.dir.resolve()
    repo_root = _repo_root()

    actions: list[str] = []
    actions.extend(
        _ensure_entry_files(
            target_dir=target_dir,
            name=name,
            force=args.force,
            dry_run=args.dry_run,
        )
    )
    actions.append(_update_pages_file(target_dir=target_dir, name=name, dry_run=args.dry_run))
    actions.append(
        _update_special_index(
            repo_root=repo_root,
            target_dir=target_dir,
            name=name,
            dry_run=args.dry_run,
        )
    )

    print("OK")
    for action in actions:
        print(f"- {action}")


if __name__ == "__main__":
    main()

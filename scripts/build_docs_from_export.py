import argparse
import shutil
from pathlib import Path


def _run_clean(docs_dir: Path) -> None:
    # Run in a subprocess so this script stays simple and works when executed directly.
    import subprocess
    import sys

    cleaner = Path(__file__).with_name("rename_and_relink.py")
    subprocess.run([sys.executable, str(cleaner), "--docs", str(docs_dir)], check=True)


def _run_organize_songshi(docs_dir: Path) -> None:
    import subprocess
    import sys

    organizer = Path(__file__).with_name("organize_songshi.py")
    if not organizer.exists():
        return
    subprocess.run(
        [sys.executable, str(organizer), "--docs", str(docs_dir)], check=True
    )


def _run_final_relink(docs_dir: Path) -> None:
    import subprocess
    import sys

    relinker = Path(__file__).with_name("final_relink.py")
    if not relinker.exists():
        return
    subprocess.run(
        [sys.executable, str(relinker), "--docs", str(docs_dir)], check=True
    )


def _run_organize_song_sections(docs_dir: Path) -> None:
    import subprocess
    import sys

    organizer = Path(__file__).with_name("organize_song_sections.py")
    if not organizer.exists():
        return
    subprocess.run(
        [sys.executable, str(organizer), "--docs", str(docs_dir)], check=True
    )


def _pick_index_md(src_root: Path) -> Path:
    # Prefer a single top-level .md file (Notion export often has exactly one).
    md_files = [
        p for p in src_root.iterdir() if p.is_file() and p.suffix.lower() == ".md"
    ]
    if not md_files:
        raise FileNotFoundError(f"No top-level .md file found in: {src_root}")

    # Heuristic: prefer one that starts with '松 ' or is named exactly '松.md'.
    for p in md_files:
        if p.name == "松.md" or p.name.startswith("松 "):
            return p
    if len(md_files) == 1:
        return md_files[0]
    names = ", ".join(sorted(p.name for p in md_files))
    raise RuntimeError(
        "Multiple top-level .md files found; pass --index to choose one. "
        f"Candidates: {names}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Copy Notion export into MkDocs docs/, then by default clean links/file names "
            "and organize 松一级目录 + 松史子目录。"
        )
    )
    parser.add_argument(
        "--src",
        type=Path,
        required=True,
        help="Notion export root directory (contains '松/' and a top-level '松 ....md').",
    )
    parser.add_argument(
        "--dst",
        type=Path,
        required=True,
        help="MkDocs project root (contains mkdocs.yml). docs/ will be created/overwritten.",
    )
    parser.add_argument(
        "--index",
        type=Path,
        default=None,
        help="Optional: explicit path to the top-level index markdown inside --src.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="If set, delete existing docs/ before copying.",
    )
    parser.add_argument(
        "--skip-clean",
        action="store_true",
        help="Skip cleanup step (strip Notion IDs and relink).",
    )
    parser.add_argument(
        "--skip-organize-songshi",
        action="store_true",
        help="Skip 松史 grouping step (split by headings into subfolders).",
    )
    parser.add_argument(
        "--skip-organize-song-sections",
        action="store_true",
        help="Skip folderizing docs/松/*.md into matching section folders.",
    )
    parser.add_argument(
        "--skip-final-relink",
        action="store_true",
        help="Skip final link normalization pass.",
    )
    args = parser.parse_args()

    src_root = args.src.resolve()
    dst_root = args.dst.resolve()
    docs_dir = dst_root / "docs"

    if args.force and docs_dir.exists():
        shutil.rmtree(docs_dir)
    docs_dir.mkdir(parents=True, exist_ok=True)

    index_src = args.index.resolve() if args.index else _pick_index_md(src_root)
    if not index_src.exists():
        raise FileNotFoundError(f"Index file not found: {index_src}")

    # 1) Copy the top-level index to docs/index.md
    shutil.copy2(index_src, docs_dir / "index.md")

    # 2) Copy the main content folder(s) as-is. Prefer the folder named '松'.
    pine_dir = src_root / "松"
    if not pine_dir.exists() or not pine_dir.is_dir():
        raise FileNotFoundError(f"Expected directory '松' not found in: {src_root}")

    dst_pine_dir = docs_dir / "松"
    if dst_pine_dir.exists():
        shutil.rmtree(dst_pine_dir)
    shutil.copytree(pine_dir, dst_pine_dir)

    if not args.skip_clean:
        _run_clean(docs_dir)
    if not args.skip_organize_song_sections:
        _run_organize_song_sections(docs_dir)
    if not args.skip_organize_songshi:
        _run_organize_songshi(docs_dir)
    if not args.skip_final_relink:
        _run_final_relink(docs_dir)

    print("OK")
    print(f"- Wrote: {docs_dir / 'index.md'}")
    print(f"- Copied: {dst_pine_dir}")
    if not args.skip_clean:
        print(f"- Cleaned: {docs_dir}")
    if not args.skip_organize_song_sections:
        print(f"- Organized 松一级目录: {docs_dir}")
    if not args.skip_organize_songshi:
        print(f"- Organized 松史: {docs_dir}")
    if not args.skip_final_relink:
        print(f"- Final relinked: {docs_dir}")


if __name__ == "__main__":
    main()

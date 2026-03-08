import argparse
from pathlib import Path

from gallery_utils import apply_gallery_layout, collect_markdown_files

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Auto-convert consecutive images into GitHub-friendly inline HTML rows."
    )
    parser.add_argument(
        "--path",
        type=Path,
        default=Path("docs"),
        help="Target markdown file or directory (default: docs)",
    )
    parser.add_argument(
        "--min-group",
        type=int,
        default=2,
        help="Minimum consecutive image count to convert (default: 2)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview file changes without writing files.",
    )
    args = parser.parse_args()

    if args.min_group < 2:
        raise ValueError("--min-group must be >= 2")

    path = args.path.resolve()
    if path.is_file():
        files = [path] if path.suffix.lower() == ".md" else []
    else:
        files = collect_markdown_files(path, changed_only=False)

    updated_files, updated_groups = apply_gallery_layout(
        files,
        min_group=args.min_group,
        dry_run=args.dry_run,
    )

    mode = "DRY-RUN" if args.dry_run else "OK"
    print(mode)
    print(f"- Scanned files: {len(files)}")
    print(f"- Updated files: {updated_files}")
    print(f"- Converted groups: {updated_groups}")


if __name__ == "__main__":
    main()

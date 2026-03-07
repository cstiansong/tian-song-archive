import argparse
import shutil
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import a Notion-export folder into export/ (keeps original structure)."
    )
    parser.add_argument(
        "--src",
        type=Path,
        required=True,
        help="Notion export root (contains '松/' and a top-level '松 ....md').",
    )
    parser.add_argument(
        "--export",
        type=Path,
        default=Path("export"),
        help="Destination export directory (default: export).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="If set, delete destination export/ first.",
    )
    args = parser.parse_args()

    src_root = args.src.resolve()
    export_dir = args.export.resolve()

    if args.force and export_dir.exists():
        shutil.rmtree(export_dir)
    export_dir.mkdir(parents=True, exist_ok=True)

    # Copy folder '松'
    src_pine = src_root / "松"
    if not src_pine.is_dir():
        raise FileNotFoundError(f"Expected directory not found: {src_pine}")
    dst_pine = export_dir / "松"
    if dst_pine.exists():
        shutil.rmtree(dst_pine)
    shutil.copytree(src_pine, dst_pine)

    # Copy top-level .md files (kept as-is; build_docs_from_export.py will choose index)
    for md in src_root.iterdir():
        if md.is_file() and md.suffix.lower() == ".md":
            shutil.copy2(md, export_dir / md.name)

    print("OK")
    print(f"- Export dir: {export_dir}")


if __name__ == "__main__":
    main()

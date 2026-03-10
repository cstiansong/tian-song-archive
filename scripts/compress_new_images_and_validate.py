import argparse
import subprocess
from pathlib import Path

from gallery_utils import apply_gallery_layout, collect_markdown_files
from media_utils import collect_images, compress_images, format_bytes


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Compress newly added/changed images first, then run mkdocs build --strict."
        )
    )
    parser.add_argument("--docs", type=Path, default=Path("docs"), help="Docs directory")
    parser.add_argument(
        "--all-images",
        action="store_true",
        help="Compress all images under docs/ (not only changed/new).",
    )
    parser.add_argument(
        "--base-ref",
        default="HEAD~1",
        help="Git base ref used when checking changed files (default: HEAD~1).",
    )
    parser.add_argument("--image-max-width", type=int, default=1400)
    parser.add_argument("--jpg-quality", type=int, default=68)
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument(
        "--skip-gallery-layout",
        action="store_true",
        help="Skip auto gallery formatting (GitHub-friendly <p><img width=...>).",
    )
    parser.add_argument(
        "--all-markdown",
        action="store_true",
        help="Apply gallery formatting to all markdown files under docs/.",
    )
    parser.add_argument("--gallery-min-group", type=int, default=2)
    args = parser.parse_args()

    docs_dir = args.docs.resolve()
    if not docs_dir.exists() or not docs_dir.is_dir():
        raise FileNotFoundError(f"Docs directory not found: {docs_dir}")

    if args.jpg_quality < 1 or args.jpg_quality > 95:
        raise ValueError("--jpg-quality must be between 1 and 95")
    if args.image_max_width < 0:
        raise ValueError("--image-max-width must be >= 0")
    if args.workers < 1:
        raise ValueError("--workers must be >= 1")
    if args.gallery_min_group < 2:
        raise ValueError("--gallery-min-group must be >= 2")

    gallery_candidates = collect_markdown_files(
        docs_dir,
        changed_only=not args.all_markdown,
        base_ref=args.base_ref,
    )
    gallery_files_updated = 0
    gallery_groups_updated = 0
    if not args.skip_gallery_layout:
        gallery_files_updated, gallery_groups_updated = apply_gallery_layout(
            gallery_candidates,
            min_group=args.gallery_min_group,
            dry_run=False,
        )

    image_files = collect_images(
        docs_dir,
        changed_only=not args.all_images,
        base_ref=args.base_ref,
    )

    if image_files:
        scanned, updated, errors, total_before, total_after = compress_images(
            image_files,
            max_width=args.image_max_width,
            jpg_quality=args.jpg_quality,
            workers=args.workers,
            progress_desc="compress-new",
        )
    else:
        scanned, updated, errors, total_before, total_after = (0, 0, 0, 0, 0)

    saved = max(total_before - total_after, 0)
    ratio = (saved / total_before * 100.0) if total_before > 0 else 0.0
    print("OK")
    print(f"- Markdown candidates: {len(gallery_candidates)}")
    print(
        "- Gallery formatting: "
        f"updated_files={gallery_files_updated}, converted_groups={gallery_groups_updated}"
    )
    print(f"- Image candidates: {len(image_files)}")
    print(f"- Compressed images: scanned={scanned}, updated={updated}, errors={errors}")
    print(
        "- Image size: "
        f"before={format_bytes(total_before)}, "
        f"after={format_bytes(total_after)}, "
        f"saved={format_bytes(saved)} ({ratio:.1f}%)"
    )

    subprocess.run(
        [
            "python",
            "scripts/check_gallery_format.py",
            "--docs",
            str(docs_dir),
        ],
        check=True,
    )
    subprocess.run(["mkdocs", "build", "--strict"], check=True)


if __name__ == "__main__":
    main()

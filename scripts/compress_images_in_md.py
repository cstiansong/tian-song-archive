import argparse
import re
import urllib.parse
from pathlib import Path

from media_utils import compress_images, format_bytes


MD_IMG_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
HTML_IMG_RE = re.compile(r'<img[^>]*\bsrc="([^"]+)"', re.IGNORECASE)


def _collect_image_candidates(md_path: Path) -> tuple[list[Path], list[str]]:
    text = md_path.read_text(encoding="utf-8")
    raw_refs: set[str] = set()

    for m in MD_IMG_RE.finditer(text):
        raw_refs.add(m.group(1).strip())
    for m in HTML_IMG_RE.finditer(text):
        raw_refs.add(m.group(1).strip())

    files: set[Path] = set()
    missing: list[str] = []
    for ref in sorted(raw_refs):
        if not ref or ref.startswith(("http://", "https://", "data:", "#")):
            continue

        rel = urllib.parse.unquote(ref)
        target = (md_path.parent / rel).resolve()
        if target.exists() and target.is_file():
            if target.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
                files.add(target)
        else:
            missing.append(ref)

    return sorted(files), missing


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compress only images referenced by one markdown file."
    )
    parser.add_argument("--md", type=Path, required=True, help="Target markdown file")
    parser.add_argument("--image-max-width", type=int, default=1400)
    parser.add_argument("--jpg-quality", type=int, default=68)
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    md_path = args.md.resolve()
    if not md_path.exists() or not md_path.is_file():
        raise FileNotFoundError(f"Markdown file not found: {md_path}")
    if args.jpg_quality < 1 or args.jpg_quality > 95:
        raise ValueError("--jpg-quality must be between 1 and 95")
    if args.image_max_width < 0:
        raise ValueError("--image-max-width must be >= 0")
    if args.workers < 1:
        raise ValueError("--workers must be >= 1")

    images, missing = _collect_image_candidates(md_path)

    print("OK")
    print(f"- Markdown: {md_path}")
    print(f"- Referenced image files: {len(images)}")
    if missing:
        print(f"- Missing refs: {len(missing)}")
        for ref in missing[:20]:
            print(f"  - {ref}")
        if len(missing) > 20:
            print(f"  ... and {len(missing) - 20} more")

    if args.dry_run:
        print("- Dry run only, skipped compression")
        return

    scanned, updated, errors, total_before, total_after = compress_images(
        images,
        max_width=args.image_max_width,
        jpg_quality=args.jpg_quality,
        workers=args.workers,
        progress_desc="compress-md",
    )
    saved = max(total_before - total_after, 0)
    ratio = (saved / total_before * 100.0) if total_before > 0 else 0.0

    print(f"- Compressed images: scanned={scanned}, updated={updated}, errors={errors}")
    print(
        "- Image size: "
        f"before={format_bytes(total_before)}, "
        f"after={format_bytes(total_after)}, "
        f"saved={format_bytes(saved)} ({ratio:.1f}%)"
    )


if __name__ == "__main__":
    main()

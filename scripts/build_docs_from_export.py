import argparse
import os
import subprocess
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from media_utils import compress_images_under_dir, format_bytes


def _compress_videos(
    docs_dir: Path,
    *,
    crf: int,
    max_height: int,
    workers: int,
    ffmpeg_preset: str,
    copy_only: bool,
) -> tuple[int, int, int, int, int]:
    try:
        from tqdm import tqdm
    except ImportError as exc:
        raise RuntimeError(
            "Video compression requested but tqdm is not installed. "
            "Install dependencies via: pip install -r requirements.txt"
        ) from exc

    scanned = 0
    compressed = 0
    errors = 0
    total_before = 0
    total_after = 0

    def _process_video(p: Path) -> tuple[int, int, int, int]:
        before = p.stat().st_size
        tmp = p.with_name(f"{p.stem}.compressed{p.suffix}")

        cmd = [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(p),
            "-map_metadata",
            "-1",
            "-map_chapters",
            "-1",
        ]

        if copy_only:
            cmd.extend(["-c", "copy", str(tmp)])
        else:
            vf = f"scale=-2:min(ih\\,{max_height})" if max_height > 0 else "null"
            cmd.extend(["-vf", vf])
            if p.suffix.lower() == ".webm":
                webm_crf = min(max(crf, 20), 40)
                cmd.extend(
                    [
                        "-c:v",
                        "libvpx-vp9",
                        "-b:v",
                        "0",
                        "-crf",
                        str(webm_crf),
                        "-row-mt",
                        "1",
                        "-deadline",
                        "good",
                        "-cpu-used",
                        "4",
                        "-c:a",
                        "libopus",
                        "-b:a",
                        "96k",
                        str(tmp),
                    ]
                )
            else:
                cmd.extend(
                    [
                        "-c:v",
                        "libx264",
                        "-preset",
                        ffmpeg_preset,
                        "-crf",
                        str(crf),
                        "-pix_fmt",
                        "yuv420p",
                        "-movflags",
                        "+faststart",
                        "-c:a",
                        "aac",
                        "-b:a",
                        "128k",
                        str(tmp),
                    ]
                )

        try:
            subprocess.run(cmd, check=True)
            after = tmp.stat().st_size
            if after < before:
                os.replace(tmp, p)
                return 1, 1, before, after
            tmp.unlink(missing_ok=True)
            return 1, 0, before, before
        except Exception:
            tmp.unlink(missing_ok=True)
            return 1, -1, before, before

    video_suffixes = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm", ".wmv", ".flv"}
    video_files = [
        p
        for p in docs_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in video_suffixes
    ]
    progress = tqdm(total=len(video_files), desc="video", unit="vid")
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(_process_video, p) for p in video_files]
        for future in as_completed(futures):
            done, updated, before, after = future.result()
            scanned += done
            total_before += before
            total_after += after
            if updated < 0:
                errors += 1
            else:
                compressed += updated
            progress.update(1)
    progress.close()

    return scanned, compressed, errors, total_before, total_after


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
    parser.add_argument(
        "--compress-media",
        action="store_true",
        help="Compress both images and videos under docs/ after copying from export.",
    )
    parser.add_argument(
        "--compress-images",
        action="store_true",
        help="Compress images under docs/ after copying from export.",
    )
    parser.add_argument(
        "--compress-videos",
        action="store_true",
        help="Compress videos under docs/ after copying from export.",
    )
    parser.add_argument(
        "--compress-preset",
        choices=["strict", "balanced", "archival"],
        default="strict",
        help="Compression preset (default: strict).",
    )
    parser.add_argument(
        "--image-max-width",
        type=int,
        default=None,
        help="Resize images wider than this value in pixels (0 means no resize).",
    )
    parser.add_argument(
        "--jpg-quality",
        type=int,
        default=None,
        help="JPEG/WebP quality used during image compression (1-95).",
    )
    parser.add_argument(
        "--compress-workers",
        type=int,
        default=16,
        help="Worker threads used for image compression (default: 16).",
    )
    parser.add_argument(
        "--video-workers",
        type=int,
        default=4,
        help="Worker threads used for video compression (default: 4).",
    )
    parser.add_argument(
        "--video-crf",
        type=int,
        default=None,
        help="CRF for video compression (lower is better quality).",
    )
    parser.add_argument(
        "--video-max-height",
        type=int,
        default=None,
        help="Resize videos taller than this value in pixels (0 means no resize).",
    )
    parser.add_argument(
        "--video-ffmpeg-preset",
        choices=["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"],
        default=None,
        help="ffmpeg preset for H.264 encoding.",
    )
    args = parser.parse_args()

    preset_map = {
        "strict": {
            "image_max_width": 1400,
            "jpg_quality": 68,
            "video_crf": 30,
            "video_max_height": 720,
            "video_ffmpeg_preset": "medium",
            "video_copy_only": False,
        },
        "balanced": {
            "image_max_width": 2000,
            "jpg_quality": 78,
            "video_crf": 26,
            "video_max_height": 1080,
            "video_ffmpeg_preset": "medium",
            "video_copy_only": False,
        },
        "archival": {
            "image_max_width": 0,
            "jpg_quality": 90,
            "video_crf": 0,
            "video_max_height": 0,
            "video_ffmpeg_preset": "medium",
            "video_copy_only": True,
        },
    }
    preset = preset_map[args.compress_preset]

    image_max_width = (
        args.image_max_width if args.image_max_width is not None else preset["image_max_width"]
    )
    jpg_quality = args.jpg_quality if args.jpg_quality is not None else preset["jpg_quality"]
    video_crf = args.video_crf if args.video_crf is not None else preset["video_crf"]
    video_max_height = (
        args.video_max_height if args.video_max_height is not None else preset["video_max_height"]
    )
    video_ffmpeg_preset = (
        args.video_ffmpeg_preset
        if args.video_ffmpeg_preset is not None
        else preset["video_ffmpeg_preset"]
    )
    video_copy_only = bool(preset["video_copy_only"])

    if jpg_quality < 1 or jpg_quality > 95:
        raise ValueError("--jpg-quality must be between 1 and 95")
    if image_max_width < 0:
        raise ValueError("--image-max-width must be >= 0")
    if args.compress_workers < 1:
        raise ValueError("--compress-workers must be >= 1")
    if args.video_workers < 1:
        raise ValueError("--video-workers must be >= 1")
    if video_crf < 0 or video_crf > 51:
        raise ValueError("--video-crf must be between 0 and 51")
    if video_max_height < 0:
        raise ValueError("--video-max-height must be >= 0")

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

    compress_images = args.compress_images or args.compress_media
    compress_videos = args.compress_videos or args.compress_media

    img_stats: tuple[int, int, int, int, int] | None = None
    video_stats: tuple[int, int, int, int, int] | None = None
    ffmpeg_missing = False
    if compress_images:
        img_stats = compress_images_under_dir(
            docs_dir=docs_dir,
            max_width=image_max_width,
            jpg_quality=jpg_quality,
            workers=args.compress_workers,
            progress_desc="compress",
        )
    if compress_videos:
        if shutil.which("ffmpeg") is None:
            ffmpeg_missing = True
        else:
            video_stats = _compress_videos(
                docs_dir=docs_dir,
                crf=video_crf,
                max_height=video_max_height,
                workers=args.video_workers,
                ffmpeg_preset=video_ffmpeg_preset,
                copy_only=video_copy_only,
            )

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
    if img_stats is not None:
        scanned, compressed, errors, total_before, total_after = img_stats
        saved = max(total_before - total_after, 0)
        ratio = (saved / total_before * 100.0) if total_before > 0 else 0.0
        print(
            "- Compressed images: "
            f"scanned={scanned}, updated={compressed}, errors={errors}"
        )
        print(
            "- Image size: "
            f"before={format_bytes(total_before)}, "
            f"after={format_bytes(total_after)}, "
            f"saved={format_bytes(saved)} ({ratio:.1f}%)"
        )
    if video_stats is not None:
        scanned, compressed, errors, total_before, total_after = video_stats
        saved = max(total_before - total_after, 0)
        ratio = (saved / total_before * 100.0) if total_before > 0 else 0.0
        print(
            "- Compressed videos: "
            f"scanned={scanned}, updated={compressed}, errors={errors}"
        )
        print(
            "- Video size: "
            f"before={format_bytes(total_before)}, "
            f"after={format_bytes(total_after)}, "
            f"saved={format_bytes(saved)} ({ratio:.1f}%)"
        )
    if ffmpeg_missing:
        print("- Warning: ffmpeg not found, skipped video compression")
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

import os
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def format_bytes(num: int) -> str:
    units = ["B", "KB", "MB", "GB"]
    value = float(num)
    for unit in units:
        if value < 1024.0 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)}{unit}"
            return f"{value:.2f}{unit}"
        value /= 1024.0
    return f"{num}B"


def git_changed_files(repo_root: Path, base_ref: str) -> set[Path]:
    changed: set[Path] = set()

    diff_cmd = [
        "git",
        "diff",
        "--name-only",
        "--diff-filter=AM",
        f"{base_ref}...HEAD",
    ]
    diff = subprocess.run(diff_cmd, cwd=repo_root, capture_output=True, text=True)
    if diff.returncode == 0:
        for line in diff.stdout.splitlines():
            if line.strip():
                changed.add((repo_root / line.strip()).resolve())

    untracked_cmd = ["git", "ls-files", "--others", "--exclude-standard"]
    untracked = subprocess.run(
        untracked_cmd, cwd=repo_root, capture_output=True, text=True, check=True
    )
    for line in untracked.stdout.splitlines():
        if line.strip():
            changed.add((repo_root / line.strip()).resolve())

    return changed


def collect_images(docs_dir: Path, changed_only: bool, base_ref: str = "HEAD~1") -> list[Path]:
    if not changed_only:
        return [
            p
            for p in docs_dir.rglob("*")
            if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES
        ]

    repo_root = docs_dir.parent
    changed = git_changed_files(repo_root, base_ref)
    images: list[Path] = []
    for p in changed:
        if not p.exists() or not p.is_file():
            continue
        if p.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        try:
            _ = p.relative_to(docs_dir)
        except ValueError:
            continue
        images.append(p)
    return sorted(images)


def compress_images(
    image_files: list[Path],
    *,
    max_width: int,
    jpg_quality: int,
    workers: int,
    progress_desc: str,
) -> tuple[int, int, int, int, int]:
    try:
        from PIL import Image  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "Image compression requires Pillow. Install with: pip install -r requirements.txt"
        ) from exc
    try:
        from tqdm import tqdm
    except ImportError as exc:
        raise RuntimeError(
            "Image compression progress requires tqdm. Install with: pip install -r requirements.txt"
        ) from exc

    scanned = 0
    updated = 0
    errors = 0
    total_before = 0
    total_after = 0

    def _process_one(p: Path) -> tuple[int, int, int, int]:
        tmp = p.with_name(f"{p.stem}.tmp{p.suffix}")
        try:
            with Image.open(p) as im:
                original_mode = im.mode
                original_size = im.size
                resized = False

                if max_width > 0 and im.width > max_width:
                    new_height = int(im.height * (max_width / im.width))
                    im = im.resize((max_width, new_height), Image.Resampling.LANCZOS)
                    resized = True

                suffix = p.suffix.lower()
                save_kwargs: dict[str, object]

                if suffix in {".jpg", ".jpeg"}:
                    if im.mode in {"RGBA", "LA", "P"}:
                        im = im.convert("RGB")
                    save_kwargs = {
                        "quality": jpg_quality,
                        "optimize": True,
                        "progressive": True,
                        "exif": b"",
                        "icc_profile": None,
                    }
                elif suffix == ".png":
                    save_kwargs = {
                        "optimize": True,
                        "compress_level": 9,
                    }
                else:  # .webp
                    if im.mode in {"LA", "P"}:
                        im = im.convert("RGBA")
                    save_kwargs = {
                        "quality": min(jpg_quality, 90),
                        "method": 6,
                        "exif": b"",
                        "icc_profile": None,
                    }

                before = p.stat().st_size
                im.save(tmp, **save_kwargs)
                after = tmp.stat().st_size

                did_update = int(
                    after < before
                    or resized
                    or im.mode != original_mode
                    or im.size != original_size
                )
                if did_update:
                    os.replace(tmp, p)
                    return 1, 1, before, after
                tmp.unlink(missing_ok=True)
                return 1, 0, before, before
        except Exception:
            tmp.unlink(missing_ok=True)
            return 1, -1, 0, 0

    progress = tqdm(total=len(image_files), desc=progress_desc, unit="img")
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(_process_one, p) for p in image_files]
        for future in as_completed(futures):
            done, did_update, before, after = future.result()
            scanned += done
            total_before += before
            total_after += after
            if did_update < 0:
                errors += 1
            else:
                updated += did_update
            progress.update(1)
    progress.close()

    return scanned, updated, errors, total_before, total_after


def compress_images_under_dir(
    docs_dir: Path,
    *,
    max_width: int,
    jpg_quality: int,
    workers: int,
    progress_desc: str,
) -> tuple[int, int, int, int, int]:
    image_files = collect_images(docs_dir, changed_only=False)
    return compress_images(
        image_files,
        max_width=max_width,
        jpg_quality=jpg_quality,
        workers=workers,
        progress_desc=progress_desc,
    )

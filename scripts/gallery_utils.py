import re
from pathlib import Path

from media_utils import git_changed_files


IMG_RE = re.compile(r"^\s*!\[(?P<alt>[^\]]*)\]\((?P<src>[^)]+)\)\s*$")


def collect_markdown_files(docs_dir: Path, changed_only: bool, base_ref: str = "HEAD~1") -> list[Path]:
    if not changed_only:
        return sorted(p for p in docs_dir.rglob("*.md") if p.is_file())

    repo_root = docs_dir.parent
    changed = git_changed_files(repo_root, base_ref)
    out: list[Path] = []
    for p in changed:
        if not p.exists() or not p.is_file():
            continue
        if p.suffix.lower() != ".md":
            continue
        try:
            _ = p.relative_to(docs_dir)
        except ValueError:
            continue
        out.append(p)
    return sorted(out)


def _render_gallery(images: list[tuple[str, str]], gap_px: int, fixed_height: int) -> list[str]:
    if len(images) == 2:
        width = "49%"
        groups = [images]
    elif len(images) == 3:
        width = "32%"
        groups = [images]
    else:
        width = "49%"
        groups = [images[i : i + 2] for i in range(0, len(images), 2)]

    out: list[str] = []
    for idx, group in enumerate(groups):
        if len(group) == 1:
            alt, src = group[0]
            out.append(f"![{alt}]({src})")
            continue

        out.append(
            f'<div style="display:flex; gap:{gap_px}px; flex-wrap:wrap; align-items:flex-start;">'
        )
        for alt, src in group:
            out.append(
                "  "
                f'<img src="{src}" alt="{alt}" '
                f'style="width:{width}; height:{fixed_height}px; object-fit:contain; background:#f5f5f5;" />'
            )
        out.append("</div>")
        if idx != len(groups) - 1:
            out.append("")

    return out


def transform_gallery_blocks(
    lines: list[str], min_group: int, gap_px: int, fixed_height: int
) -> tuple[list[str], int]:
    out: list[str] = []
    i = 0
    changed_groups = 0
    in_fence = False

    while i < len(lines):
        line = lines[i]

        if line.strip().startswith("```"):
            in_fence = not in_fence
            out.append(line)
            i += 1
            continue

        if in_fence:
            out.append(line)
            i += 1
            continue

        m = IMG_RE.match(line)
        if not m:
            out.append(line)
            i += 1
            continue

        start = i
        j = i
        imgs: list[tuple[str, str]] = []
        while j < len(lines):
            cur = lines[j]
            mm = IMG_RE.match(cur)
            if mm:
                imgs.append((mm.group("alt"), mm.group("src")))
                j += 1
                continue
            if cur.strip() == "":
                j += 1
                continue
            break

        if len(imgs) >= min_group:
            out.extend(_render_gallery(imgs, gap_px, fixed_height))
            changed_groups += 1
        else:
            out.extend(lines[start:j])
        i = j

    return out, changed_groups


def apply_gallery_layout(
    files: list[Path], min_group: int, gap_px: int, fixed_height: int, dry_run: bool
) -> tuple[int, int]:
    updated_files = 0
    updated_groups = 0

    for md in files:
        raw = md.read_text(encoding="utf-8")
        lines = raw.splitlines()
        new_lines, groups = transform_gallery_blocks(lines, min_group, gap_px, fixed_height)
        if groups == 0:
            continue

        updated_files += 1
        updated_groups += groups
        if not dry_run:
            md.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    return updated_files, updated_groups

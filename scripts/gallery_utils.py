import re
import urllib.parse
from pathlib import Path

from media_utils import git_changed_files


IMG_RE = re.compile(r"^\s*!\[(?P<alt>[^\]]*)\]\((?P<src>[^)]+)\)\s*$")
DIV_START_RE = re.compile(r"^\s*<div\b[^>]*>\s*$", re.IGNORECASE)
DIV_END_RE = re.compile(r"^\s*</div>\s*$", re.IGNORECASE)
IMG_TAG_RE = re.compile(r'<img\b[^>]*\bsrc="(?P<src>[^"]+)"[^>]*>', re.IGNORECASE)
ALT_ATTR_RE = re.compile(r'\balt="(?P<alt>[^"]*)"', re.IGNORECASE)
TABLE_ANY_RE = re.compile(r"^\s*\|.*\|\s*$")
TABLE_SEP_RE = re.compile(r"^\s*\|\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|\s*$")
IMG_INLINE_RE = re.compile(r"!\[(?P<alt>[^\]]*)\]\((?P<src>[^)]+)\)")
P_START_RE = re.compile(r"^\s*<p>\s*$", re.IGNORECASE)
P_END_RE = re.compile(r"^\s*</p>\s*$", re.IGNORECASE)


_GENERIC_ALT_RE = re.compile(r"^\s*Untitled(?:\s*\d+)?\s*$", re.IGNORECASE)


def _default_alt_from_src(src: str) -> str:
    # Prefer a stable, descriptive alt for Notion-exported assets.
    # Use the decoded basename so "%20" becomes a space in alt text.
    try:
        decoded = urllib.parse.unquote(src)
    except Exception:
        decoded = src
    name = Path(decoded).name
    return name or ""


def _normalize_alt(alt: str, src: str) -> str:
    a = (alt or "").strip()
    if not a or _GENERIC_ALT_RE.match(a):
        return _default_alt_from_src(src)
    return a


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


def _render_gallery(images: list[tuple[str, str]]) -> list[str]:
    if len(images) <= 3:
        groups = [images]
    else:
        groups = [images[i : i + 2] for i in range(0, len(images), 2)]

    out: list[str] = []
    for idx, group in enumerate(groups):
        if len(group) == 1:
            alt, src = group[0]
            alt = _normalize_alt(alt, src)
            out.append(f"![{alt}]({src})")
            continue

        if len(group) == 2:
            width = "49%"
        else:
            width = "32%"
        out.append("<p>")
        for alt, src in group:
            alt = _normalize_alt(alt, src)
            out.append(f'  <img src="{src}" alt="{alt}" width="{width}">')
        out.append("</p>")
        if idx != len(groups) - 1:
            out.append("")

    return out


def _quote_path(path_str: str) -> str:
    return urllib.parse.quote(path_str, safe="/._-~")


def _normalize_image_src(md_path: Path, src: str) -> str:
    if src.startswith(("http://", "https://", "data:", "#", "/")):
        return src

    decoded = urllib.parse.unquote(src)
    parts = [p for p in Path(decoded).parts if p not in {"", "."}]
    if len(parts) < 2:
        return src

    # Preferred style: when images live in sibling folder named after the page
    # ("X.md" + "X/<file>"), use "<file>" in <img src> blocks.
    first = parts[0]
    md_stem = md_path.stem
    if first != md_stem:
        return src

    stripped_decoded = "/".join(parts[1:])
    if not stripped_decoded:
        return src
    return _quote_path(stripped_decoded)


def _normalize_images_for_md(md_path: Path, images: list[tuple[str, str]]) -> list[tuple[str, str]]:
    return [(alt, _normalize_image_src(md_path, src)) for alt, src in images]


def _extract_images_from_div_block(block_lines: list[str]) -> list[tuple[str, str]]:
    images: list[tuple[str, str]] = []
    for line in block_lines:
        m = IMG_TAG_RE.search(line)
        if not m:
            continue
        src = m.group("src")
        alt_match = ALT_ATTR_RE.search(line)
        alt = alt_match.group("alt") if alt_match else ""
        alt = _normalize_alt(alt, src)
        images.append((alt, src))
    return images


def _extract_images_from_p_block(block_lines: list[str]) -> list[tuple[str, str]]:
    images: list[tuple[str, str]] = []
    for line in block_lines:
        m = IMG_TAG_RE.search(line)
        if not m:
            continue
        src = m.group("src")
        alt_match = ALT_ATTR_RE.search(line)
        alt = alt_match.group("alt") if alt_match else ""
        alt = _normalize_alt(alt, src)
        images.append((alt, src))
    return images


def _extract_images_from_table_block(lines: list[str], start: int) -> tuple[list[tuple[str, str]], int]:
    if start + 2 >= len(lines):
        return [], start
    if not TABLE_ANY_RE.match(lines[start]):
        return [], start
    if not TABLE_SEP_RE.match(lines[start + 1]):
        return [], start
    if not TABLE_ANY_RE.match(lines[start + 2]):
        return [], start

    row = lines[start + 2]
    images: list[tuple[str, str]] = []
    for m in IMG_INLINE_RE.finditer(row):
        images.append((m.group("alt"), m.group("src")))
    if not images:
        return [], start
    return images, start + 2


def transform_gallery_blocks(md_path: Path, lines: list[str], min_group: int) -> tuple[list[str], int]:
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

        if P_START_RE.match(line):
            start = i
            j = i + 1
            while j < len(lines) and not P_END_RE.match(lines[j]):
                j += 1
            if j < len(lines):
                block = lines[start : j + 1]
                imgs_in_p = _extract_images_from_p_block(block)
                if len(imgs_in_p) >= min_group:
                    out.extend(_render_gallery(_normalize_images_for_md(md_path, imgs_in_p)))
                    if j + 1 < len(lines) and lines[j + 1].strip() != "":
                        out.append("")
                    changed_groups += 1
                    i = j + 1
                    continue
            out.append(line)
            i += 1
            continue

        table_imgs, table_end = _extract_images_from_table_block(lines, i)
        if len(table_imgs) >= min_group:
            out.extend(_render_gallery(_normalize_images_for_md(md_path, table_imgs)))
            if table_end + 1 < len(lines) and lines[table_end + 1].strip() != "":
                out.append("")
            changed_groups += 1
            i = table_end + 1
            continue

        if DIV_START_RE.match(line):
            start = i
            j = i + 1
            while j < len(lines) and not DIV_END_RE.match(lines[j]):
                j += 1
            if j < len(lines):
                block = lines[start : j + 1]
                imgs_in_div = _extract_images_from_div_block(block)
                if len(imgs_in_div) >= min_group:
                    out.extend(_render_gallery(_normalize_images_for_md(md_path, imgs_in_div)))
                    if j + 1 < len(lines) and lines[j + 1].strip() != "":
                        out.append("")
                    changed_groups += 1
                    i = j + 1
                    continue
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
            out.extend(_render_gallery(_normalize_images_for_md(md_path, imgs)))
            if j < len(lines) and lines[j].strip() != "":
                out.append("")
            changed_groups += 1
        else:
            out.extend(lines[start:j])
        i = j

    return out, changed_groups


def apply_gallery_layout(
    files: list[Path], min_group: int, dry_run: bool
) -> tuple[int, int]:
    updated_files = 0
    updated_groups = 0

    for md in files:
        raw = md.read_text(encoding="utf-8")
        lines = raw.splitlines()
        new_lines, groups = transform_gallery_blocks(md, lines, min_group)
        if groups == 0:
            continue

        new_text = "\n".join(new_lines) + "\n"
        if new_text == raw:
            continue

        updated_files += 1
        updated_groups += groups
        if not dry_run:
            md.write_text(new_text, encoding="utf-8")

    return updated_files, updated_groups

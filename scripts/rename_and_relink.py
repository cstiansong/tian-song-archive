import argparse
import os
import re
import urllib.parse
from dataclasses import dataclass
from pathlib import Path


HEX32_RE = re.compile(r"^(?P<stem>.+?)\s+(?P<hex>[0-9a-f]{32})(?P<suffix>_all)?$", re.IGNORECASE)
MD_LINK_RE = re.compile(r"(?P<prefix>!?\[[^\]]*\]\()(?P<target>[^)]+)(?P<suffix>\))")


@dataclass(frozen=True)
class Rename:
    old_rel: str
    new_rel: str


def _safe_rel_posix(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _strip_hex_suffix(name: str) -> str | None:
    # Works on stem without extension.
    m = HEX32_RE.match(name)
    if not m:
        return None
    stem = m.group("stem")
    suffix = m.group("suffix") or ""
    return f"{stem}{suffix}"


def _strip_hex_from_filename(filename: str) -> tuple[str | None, str | None]:
    """Return (stripped_filename, hex32) for a single path component.

    Works for both files and directories. For files, preserves extension.
    """
    p = Path(filename)
    ext = p.suffix
    stem = p.stem if ext else filename
    stripped_stem = _strip_hex_suffix(stem)
    if not stripped_stem:
        return None, None
    m = HEX32_RE.match(stem)
    hex32 = m.group("hex") if m else None
    if ext:
        return f"{stripped_stem}{ext}", hex32
    return stripped_stem, hex32


def _plan_renames(docs_root: Path) -> list[tuple[Path, Path]]:
    planned: list[tuple[Path, Path]] = []
    used: set[str] = set()

    # Walk bottom-up so children are handled before parent dirs.
    for p in sorted(docs_root.rglob("*"), key=lambda x: len(x.as_posix()), reverse=True):
        if p.name in {".DS_Store", ".pages"}:
            continue

        is_dir = p.is_dir()
        old_name = p.name

        if is_dir:
            new_stem = _strip_hex_suffix(old_name)
            if not new_stem:
                continue
            new_name = new_stem
            candidate = p.with_name(new_name)
        else:
            ext = p.suffix
            stem = p.stem
            new_stem = _strip_hex_suffix(stem)
            if not new_stem:
                continue
            new_name = f"{new_stem}{ext}"
            candidate = p.with_name(new_name)

        old_rel = _safe_rel_posix(p, docs_root)
        new_rel = _safe_rel_posix(candidate, docs_root)

        # Resolve collisions deterministically by appending a short id.
        if new_rel in used or candidate.exists():
            # Use original hex suffix if present.
            hex_match = HEX32_RE.match(p.stem if not is_dir else p.name)
            short = (hex_match.group("hex")[:8] if hex_match else "dup")
            if is_dir:
                candidate = p.with_name(f"{candidate.name}-{short}")
            else:
                candidate = p.with_name(f"{candidate.stem}-{short}{candidate.suffix}")
            new_rel = _safe_rel_posix(candidate, docs_root)

        used.add(new_rel)
        planned.append((p, candidate))

    return planned


def _apply_renames(planned: list[tuple[Path, Path]]) -> list[Rename]:
    mapping: list[Rename] = []
    for old, new in planned:
        if old == new:
            continue
        new.parent.mkdir(parents=True, exist_ok=True)
        os.rename(old, new)
        # mapping relative paths will be filled later by caller
        mapping.append(Rename(old_rel="", new_rel=""))
    return mapping


def _build_mapping(docs_root: Path, planned: list[tuple[Path, Path]]) -> list[Rename]:
    out: list[Rename] = []
    for old, new in planned:
        out.append(Rename(old_rel=_safe_rel_posix(old, docs_root), new_rel=_safe_rel_posix(new, docs_root)))
    # Longest paths first so more specific replacements win.
    out.sort(key=lambda r: len(r.old_rel), reverse=True)
    return out


def _split_target(target: str) -> tuple[str, str, str]:
    """Return (path, query, fragment) where query/fragment include leading ?/# if present."""
    raw = target.strip()
    if not raw:
        return "", "", ""
    if raw.startswith("#"):
        return "", "", raw

    frag = ""
    query = ""
    path_part = raw
    if "#" in path_part:
        path_part, frag = path_part.split("#", 1)
        frag = "#" + frag
    if "?" in path_part:
        path_part, query = path_part.split("?", 1)
        query = "?" + query
    return path_part, query, frag


def _is_external_target(path_part: str) -> bool:
    low = path_part.lower()
    return low.startswith(("http://", "https://", "mailto:", "tel:"))


def _quote_link_path(path_str: str) -> str:
    # Percent-encode spaces and non-ASCII safely for Markdown links.
    # Keep '/' so relative paths remain readable structurally.
    return urllib.parse.quote(path_str, safe="/%._-~")


def _norm_posix(path: Path) -> str:
    # Convert to posix-style relative path string.
    return path.as_posix()


def _try_fix_path_component(component: str) -> tuple[str, str | None] | None:
    stripped, hex32 = _strip_hex_from_filename(component)
    if not stripped:
        return None
    return stripped, hex32


def _resolve_existing_path(
    *, docs_root: Path, base_dir: Path, link_path: str, mapping: dict[str, str]
) -> Path | None:
    """Resolve link_path (possibly encoded) relative to base_dir to an existing path.

    - First tries mapping-based rewrite (old_rel -> new_rel), where old_rel/new_rel are docs-root-relative.
    - Then tries heuristic stripping of Notion 32-hex suffixes in path components.
    """
    decoded = urllib.parse.unquote(link_path)
    decoded = decoded.replace("\\", "/")
    # Only strip explicit './' prefixes; keep '../' which changes base.
    while decoded.startswith("./"):
        decoded = decoded[2:]

    # Compute a docs-root-relative candidate for mapping lookup.
    abs_guess = (docs_root / decoded) if decoded.startswith("/") else (base_dir / decoded)
    try:
        rel_guess = abs_guess.relative_to(docs_root)
        rel_guess_str = _norm_posix(rel_guess)
    except ValueError:
        rel_guess_str = ""

    if rel_guess_str and rel_guess_str in mapping:
        mapped_abs = docs_root / mapping[rel_guess_str]
        if mapped_abs.exists():
            return mapped_abs

    if abs_guess.exists():
        return abs_guess

    # Heuristic: strip hex suffixes in each component.
    parts = [p for p in Path(decoded).parts if p not in {"", "."}]
    if not parts:
        return None

    # If relative, keep it relative to base_dir.
    prefix_abs = docs_root if decoded.startswith("/") else base_dir
    fixed_parts: list[str] = []
    last_hex: str | None = None
    for i, comp in enumerate(parts):
        fixed = _try_fix_path_component(comp)
        if fixed:
            comp2, hex32 = fixed
            fixed_parts.append(comp2)
            if i == len(parts) - 1 and hex32:
                last_hex = hex32
        else:
            fixed_parts.append(comp)

    candidate = prefix_abs.joinpath(*fixed_parts)
    if candidate.exists():
        return candidate

    # Collision fallback for files: try appending -<hex8> if we have the original hex.
    if last_hex and candidate.suffix:
        alt = candidate.with_name(f"{candidate.stem}-{last_hex[:8]}{candidate.suffix}")
        if alt.exists():
            return alt

    return None


def _rewrite_target_for_file(md_path: Path, target: str, mapping: dict[str, str], docs_root: Path) -> str:
    path_part, query, frag = _split_target(target)
    if not path_part:
        return target
    if _is_external_target(path_part):
        return target

    base_dir = md_path.parent
    resolved = _resolve_existing_path(
        docs_root=docs_root, base_dir=base_dir, link_path=path_part, mapping=mapping
    )
    if not resolved:
        return target

    rel = Path(os.path.relpath(resolved, base_dir))
    rel_posix = rel.as_posix()
    return _quote_link_path(rel_posix) + query + frag


def _rewrite_markdown_file(path: Path, mapping: dict[str, str], docs_root: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    changed = False

    def repl(m: re.Match[str]) -> str:
        nonlocal changed
        target = m.group("target").strip()
        new_target = _rewrite_target_for_file(path, target, mapping, docs_root)
        if new_target != target:
            changed = True
        return f"{m.group('prefix')}{new_target}{m.group('suffix')}"

    new_text = MD_LINK_RE.sub(repl, text)
    if changed:
        path.write_text(new_text, encoding="utf-8")
    return changed


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rename Notion-exported files by stripping trailing hex IDs and fix intra-md links."
    )
    parser.add_argument(
        "--docs",
        type=Path,
        required=True,
        help="Docs root (MkDocs 'docs/' directory).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned renames only; do not change files.",
    )
    args = parser.parse_args()

    docs_root = args.docs.resolve()
    if not docs_root.exists() or not docs_root.is_dir():
        raise FileNotFoundError(f"Docs directory not found: {docs_root}")

    planned = _plan_renames(docs_root)
    mapping_list = _build_mapping(docs_root, planned)
    mapping: dict[str, str] = {r.old_rel: r.new_rel for r in mapping_list}

    if args.dry_run:
        for r in mapping_list:
            print(f"RENAME: {r.old_rel} -> {r.new_rel}")
        print(f"Total renames: {len(mapping_list)}")
        return

    # Apply renames first.
    for old, new in planned:
        os.rename(old, new)

    # Then rewrite links.
    changed_files = 0
    for md in docs_root.rglob("*.md"):
        if _rewrite_markdown_file(md, mapping, docs_root):
            changed_files += 1

    print("OK")
    print(f"- Renamed: {len(mapping_list)}")
    print(f"- Rewrote markdown files: {changed_files}")


if __name__ == "__main__":
    main()

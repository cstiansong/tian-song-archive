import argparse
import os
import re
import urllib.parse
from pathlib import Path
from itertools import product


MD_LINK_RE = re.compile(
    r"(?P<prefix>!?\[[^\]]*\]\()"
    r"(?P<target>(?:[^()\\]|\\.|\([^)]*\))+?)"
    r"(?P<suffix>\))"
)
NESTED_MD_LINK_RE = re.compile(
    r"(?P<prefix>\[\[[^\]]+\]\([^)]+\)\]\()"
    r"(?P<target>(?:[^()\\]|\\.|\([^)]*\))+?)"
    r"(?P<suffix>\))"
)
HTML_IMG_SRC_RE = re.compile(
    r"(?P<prefix><img\b[^>]*?\bsrc\s*=\s*)"
    r"(?P<quote>\"|')"
    r"(?P<target>[^\"']*)"
    r"(?P=quote)",
    re.IGNORECASE,
)
TOP_SECTIONS = {"松史", "松典", "松论", "松百科", "松录", "观松者", "趣事", "松·Gallery"}
HEX32_RE = re.compile(r"^(?P<stem>.+?)\s+[0-9a-f]{32}$", re.IGNORECASE)


def _split_target(target: str) -> tuple[str, str, str]:
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


def _is_external(path_part: str) -> bool:
    low = path_part.lower()
    return low.startswith(("http://", "https://", "mailto:", "tel:", "data:", "//"))


def _quote_path(path_str: str) -> str:
    # Do not keep '%' safe: if a filename literally contains '%' it must become '%25'
    # to survive URL decoding in MkDocs.
    return urllib.parse.quote(path_str, safe="/._-~")


def _normalize_path(path_part: str) -> str:
    p = urllib.parse.unquote(path_part).replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p


def _normalize_raw_path(path_part: str) -> str:
    p = path_part.replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p


def _resolve_mixed_encoded_path(base_dir: Path, raw_path: str) -> Path | None:
    parts = [x for x in Path(raw_path).parts if x not in {"", "."}]
    if not parts:
        return None

    alt_lists: list[list[str]] = []
    for comp in parts:
        dec = urllib.parse.unquote(comp)
        if dec != comp:
            alt_lists.append([comp, dec])
        else:
            alt_lists.append([comp])

    # Bound combinatorics for long paths.
    if len(alt_lists) > 8:
        return None

    for combo in product(*alt_lists):
        cand = base_dir.joinpath(*combo).resolve()
        if cand.exists():
            return cand
    return None


def _strip_hex_suffix(path_str: str) -> str:
    p = Path(path_str)
    if not p.name:
        return path_str
    ext = p.suffix
    stem = p.stem if ext else p.name
    m = HEX32_RE.match(stem)
    if not m:
        return path_str
    new_name = f"{m.group('stem')}{ext}"
    return str(p.with_name(new_name)).replace("\\", "/")


def _dedupe_leading_segment(decoded: str) -> str:
    parts = [x for x in Path(decoded).parts if x not in {"", "."}]
    if len(parts) >= 2 and parts[0] == parts[1]:
        return "/".join(parts[1:])
    return decoded


def _trim_current_dir_prefix(decoded: str, md_path: Path) -> str:
    parts = [x for x in Path(decoded).parts if x not in {"", "."}]
    if len(parts) < 2:
        return decoded
    if parts[0] == md_path.parent.name:
        return "/".join(parts[1:])
    return decoded


def _resolve_special_to_song_root(decoded: str, docs_root: Path) -> Path | None:
    # Remove leading ../ segments and map section references to docs/松/<section>/...
    p = decoded
    while p.startswith("../"):
        p = p[3:]
    while p.startswith("./"):
        p = p[2:]
    if not p:
        return None

    parts = Path(p).parts
    if not parts:
        return None
    if parts[0] in TOP_SECTIONS:
        cand = docs_root / "松" / p
        if cand.exists():
            return cand.resolve()
        # folderized page fallback
        if cand.suffix.lower() == ".md":
            idx = cand.with_suffix("") / "index.md"
            if idx.exists():
                return idx.resolve()
    return None


def _suffix_match(
    decoded: str,
    all_rel_files: list[Path],
) -> Path | None:
    parts = [x for x in Path(decoded).parts if x not in {"", ".", ".."}]
    if len(parts) < 2:
        return None

    # Prefer longer suffixes for better precision.
    max_k = min(4, len(parts))
    for k in range(max_k, 1, -1):
        suffix = "/".join(parts[-k:])
        hits = [rp for rp in all_rel_files if rp.as_posix().endswith(suffix)]
        if len(hits) == 1:
            return hits[0]
    return None


def _resolve_replacement(
    *,
    md_path: Path,
    raw_path: str,
    decoded: str,
    docs_root: Path,
    all_rel_files: list[Path],
    basename_index: dict[str, list[Path]],
) -> Path | None:
    # 1) Fast direct candidate relative to current md
    cand = (md_path.parent / decoded).resolve()
    if cand.exists():
        return cand

    cand_raw = (md_path.parent / raw_path).resolve()
    if cand_raw.exists():
        return cand_raw

    # 1.5) Notion-style attachment folder: "<page>.md" + "<page>/..."
    # Common when HTML <img src="Untitled 1.png"> is used.
    att = (md_path.parent / md_path.stem / decoded).resolve()
    if att.exists():
        return att
    att_raw = (md_path.parent / md_path.stem / raw_path).resolve()
    if att_raw.exists():
        return att_raw

    mixed = _resolve_mixed_encoded_path(md_path.parent, raw_path)
    if mixed is not None:
        return mixed

    deduped = _dedupe_leading_segment(decoded)
    if deduped != decoded:
        cand2 = (md_path.parent / deduped).resolve()
        if cand2.exists():
            return cand2

    trimmed = _trim_current_dir_prefix(decoded, md_path)
    if trimmed != decoded:
        cand_trim = (md_path.parent / trimmed).resolve()
        if cand_trim.exists():
            return cand_trim

    # 2) Section-aware rewrite to docs/松/<section>/...
    special = _resolve_special_to_song_root(decoded, docs_root)
    if special is not None:
        return special

    # 3) Suffix-based search (best for moved grouped items/assets)
    suffix_hit = _suffix_match(decoded, all_rel_files)
    if suffix_hit is not None:
        return docs_root / suffix_hit

    # 3.5) Try again after stripping Notion-style trailing hex id.
    stripped = _strip_hex_suffix(trimmed)
    if stripped != decoded:
        cand3 = (md_path.parent / stripped).resolve()
        if cand3.exists():
            return cand3
        special2 = _resolve_special_to_song_root(stripped, docs_root)
        if special2 is not None:
            return special2
        suffix2 = _suffix_match(stripped, all_rel_files)
        if suffix2 is not None:
            return docs_root / suffix2

    # 4) Unique basename fallback
    name = Path(decoded).name
    hits = basename_index.get(name, [])
    if len(hits) == 1:
        return docs_root / hits[0]

    # 5) Unique basename fallback after stripping trailing hex.
    stripped_name = Path(stripped).name
    if stripped_name != name:
        hits2 = basename_index.get(stripped_name, [])
        if len(hits2) == 1:
            return docs_root / hits2[0]

    return None


def _rewrite_md_file(
    *,
    md_path: Path,
    docs_root: Path,
    all_rel_files: list[Path],
    basename_index: dict[str, list[Path]],
    dry_run: bool,
) -> bool:
    text = md_path.read_text(encoding="utf-8")
    changed = False

    def repl(m: re.Match[str]) -> str:
        nonlocal changed
        target = m.group("target").strip()
        path_part, query, frag = _split_target(target)
        if not path_part or _is_external(path_part):
            return m.group(0)

        decoded = _normalize_path(path_part)
        raw_path = _normalize_raw_path(path_part)
        replacement = _resolve_replacement(
            md_path=md_path,
            raw_path=raw_path,
            decoded=decoded,
            docs_root=docs_root,
            all_rel_files=all_rel_files,
            basename_index=basename_index,
        )
        if replacement is None:
            return m.group(0)

        rel = Path(os.path.relpath(replacement, md_path.parent)).as_posix()
        new_target = _quote_path(rel) + query + frag
        if new_target != target:
            changed = True
        return f"{m.group('prefix')}{new_target}{m.group('suffix')}"

    def repl_img(m: re.Match[str]) -> str:
        nonlocal changed
        target = (m.group("target") or "").strip()
        path_part, query, frag = _split_target(target)
        if not path_part or _is_external(path_part):
            return m.group(0)

        decoded = _normalize_path(path_part)
        raw_path = _normalize_raw_path(path_part)
        replacement = _resolve_replacement(
            md_path=md_path,
            raw_path=raw_path,
            decoded=decoded,
            docs_root=docs_root,
            all_rel_files=all_rel_files,
            basename_index=basename_index,
        )
        if replacement is None:
            return m.group(0)

        # Prefer page-local asset paths for HTML <img>.
        # For a page "X.md" with assets in sibling folder "X/", MkDocs
        # commonly serves the page at ".../X/" and assets in the same directory.
        # Using "src=\"file.png\"" matches the style in docs and avoids repeating
        # the page folder name.
        page_asset_dir = md_path.parent if md_path.name == "index.md" else (md_path.parent / md_path.stem)
        try:
            replacement.relative_to(page_asset_dir)
            rel = Path(os.path.relpath(replacement, page_asset_dir)).as_posix()
        except ValueError:
            rel = Path(os.path.relpath(replacement, md_path.parent)).as_posix()

        new_target = _quote_path(rel) + query + frag
        if new_target != target:
            changed = True
        return f"{m.group('prefix')}{m.group('quote')}{new_target}{m.group('quote')}"

    new_text = MD_LINK_RE.sub(repl, text)
    new_text = NESTED_MD_LINK_RE.sub(repl, new_text)
    new_text = HTML_IMG_SRC_RE.sub(repl_img, new_text)
    if changed:
        if not dry_run:
            md_path.write_text(new_text, encoding="utf-8")
    return changed


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Final link normalization pass after docs restructuring."
    )
    parser.add_argument("--docs", type=Path, required=True, help="MkDocs docs/ directory")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Detect and report, but do not write files",
    )
    args = parser.parse_args()

    docs_root = args.docs.resolve()
    if not docs_root.exists() or not docs_root.is_dir():
        raise FileNotFoundError(f"Docs directory not found: {docs_root}")

    all_rel_files = [p.relative_to(docs_root) for p in docs_root.rglob("*") if p.is_file()]
    basename_index: dict[str, list[Path]] = {}
    for rp in all_rel_files:
        basename_index.setdefault(rp.name, []).append(rp)

    changed_files = 0
    for md in docs_root.rglob("*.md"):
        if _rewrite_md_file(
            md_path=md,
            docs_root=docs_root,
            all_rel_files=all_rel_files,
            basename_index=basename_index,
            dry_run=args.dry_run,
        ):
            changed_files += 1

    print("OK")
    print(f"- Rewrote markdown files: {changed_files}")


if __name__ == "__main__":
    main()

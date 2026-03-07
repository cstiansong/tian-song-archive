import argparse
import os
import re
import urllib.parse
from pathlib import Path


MD_LINK_RE = re.compile(r"(?P<prefix>!?\[[^\]]*\]\()(?P<target>[^)]+)(?P<suffix>\))")
TOP_SECTIONS = {"松史", "松典", "松论", "松百科", "松录", "观松者", "趣事", "松·Gallery"}


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
    return low.startswith(("http://", "https://", "mailto:", "tel:"))


def _quote_path(path_str: str) -> str:
    return urllib.parse.quote(path_str, safe="/%._-~")


def _normalize_path(path_part: str) -> str:
    p = urllib.parse.unquote(path_part).replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p


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
    decoded: str,
    docs_root: Path,
    all_rel_files: list[Path],
    basename_index: dict[str, list[Path]],
) -> Path | None:
    # 1) Fast direct candidate relative to current md
    cand = (md_path.parent / decoded).resolve()
    if cand.exists():
        return cand

    # 2) Section-aware rewrite to docs/松/<section>/...
    special = _resolve_special_to_song_root(decoded, docs_root)
    if special is not None:
        return special

    # 3) Suffix-based search (best for moved grouped items/assets)
    suffix_hit = _suffix_match(decoded, all_rel_files)
    if suffix_hit is not None:
        return docs_root / suffix_hit

    # 4) Unique basename fallback
    name = Path(decoded).name
    hits = basename_index.get(name, [])
    if len(hits) == 1:
        return docs_root / hits[0]

    return None


def _rewrite_md_file(
    *,
    md_path: Path,
    docs_root: Path,
    all_rel_files: list[Path],
    basename_index: dict[str, list[Path]],
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
        replacement = _resolve_replacement(
            md_path=md_path,
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

    new_text = MD_LINK_RE.sub(repl, text)
    if changed:
        md_path.write_text(new_text, encoding="utf-8")
    return changed


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Final link normalization pass after docs restructuring."
    )
    parser.add_argument("--docs", type=Path, required=True, help="MkDocs docs/ directory")
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
        ):
            changed_files += 1

    print("OK")
    print(f"- Rewrote markdown files: {changed_files}")


if __name__ == "__main__":
    main()

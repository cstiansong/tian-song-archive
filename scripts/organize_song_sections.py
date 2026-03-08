import argparse
import os
import re
import urllib.parse
from dataclasses import dataclass
from pathlib import Path


MD_LINK_RE = re.compile(
    r"(?P<prefix>!?\[[^\]]*\]\()"
    r"(?P<target>(?:[^()\\]|\\.|\([^)]*\))+?)"
    r"(?P<suffix>\))"
)


@dataclass(frozen=True)
class Move:
    old_abs: Path
    new_abs: Path


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
    return urllib.parse.quote(path_str, safe="/._-~")


def _iter_targets(markdown_text: str) -> list[str]:
    return [m.group("target").strip() for m in MD_LINK_RE.finditer(markdown_text)]


def _write_pages(path: Path, nav: list[str]) -> None:
    lines = ["nav:"] + [f"  - {item}" for item in nav]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _folderize_song_sections(docs_root: Path) -> list[Move]:
    song_root = docs_root / "松"
    if not song_root.exists():
        return []

    moves: list[Move] = []
    for md in song_root.glob("*.md"):
        section_dir = song_root / md.stem
        if not section_dir.is_dir():
            continue

        new_md = section_dir / "index.md"
        if new_md.exists():
            # Already folderized.
            continue

        md.rename(new_md)
        moves.append(Move(old_abs=md.resolve(), new_abs=new_md.resolve()))

    return moves


def _build_song_nav_from_index(docs_root: Path) -> list[str]:
    docs_index = docs_root / "index.md"
    song_root = docs_root / "松"
    if not docs_index.exists() or not song_root.exists():
        return []

    text = docs_index.read_text(encoding="utf-8")
    ordered: list[str] = []
    seen: set[str] = set()

    for target in _iter_targets(text):
        path_part, _, _ = _split_target(target)
        if not path_part or _is_external(path_part):
            continue

        decoded = urllib.parse.unquote(path_part).replace("\\", "/")
        p = Path(decoded)
        parts = p.parts
        if len(parts) < 2 or parts[0] != "松":
            continue

        second = parts[1]
        second_path = Path(second)

        # Decide nav entry under docs/松/ level.
        if second_path.suffix == ".md":
            stem = second_path.stem
            # If there is a directory with same name, prefer directory entry.
            if (song_root / stem).is_dir():
                entry = stem
            else:
                entry = second
        else:
            entry = second

        entry_path = song_root / entry
        # Keep only entries that exist and can appear in nav (directory or markdown).
        if not entry_path.exists():
            continue
        if entry_path.is_file() and entry_path.suffix.lower() != ".md":
            # e.g. csv should not be listed in .pages nav
            continue
        if entry in seen:
            continue
        seen.add(entry)
        ordered.append(entry)

    return ordered


def _rewrite_links_in_file(md_path: Path, move_map: dict[Path, Path]) -> bool:
    text = md_path.read_text(encoding="utf-8")
    changed = False

    def repl(m: re.Match[str]) -> str:
        nonlocal changed
        target = m.group("target").strip()
        path_part, query, frag = _split_target(target)
        if not path_part or _is_external(path_part):
            return m.group(0)

        decoded = urllib.parse.unquote(path_part).replace("\\", "/")
        while decoded.startswith("./"):
            decoded = decoded[2:]

        base_dir = md_path.parent
        resolved = (base_dir / decoded).resolve()

        # Apply move mapping if path moved.
        if resolved in move_map:
            resolved = move_map[resolved]

        # Fallback: if xxx.md now lives at xxx/index.md
        if not resolved.exists() and resolved.suffix.lower() == ".md":
            idx = resolved.with_suffix("") / "index.md"
            if idx.exists():
                resolved = idx

        if not resolved.exists():
            return m.group(0)

        rel = Path(os.path.relpath(resolved, base_dir)).as_posix()
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
        description=(
            "Folderize docs/松/*.md into docs/松/<same-name>/index.md when matching folder exists, "
            "then rewrite markdown links."
        )
    )
    parser.add_argument(
        "--docs", type=Path, required=True, help="MkDocs docs/ directory"
    )
    args = parser.parse_args()

    docs_root = args.docs.resolve()
    if not docs_root.exists() or not docs_root.is_dir():
        raise FileNotFoundError(f"Docs directory not found: {docs_root}")

    moves = _folderize_song_sections(docs_root)
    move_map: dict[Path, Path] = {m.old_abs: m.new_abs for m in moves}

    rewritten = 0
    for md in docs_root.rglob("*.md"):
        if _rewrite_links_in_file(md, move_map):
            rewritten += 1

    song_nav = _build_song_nav_from_index(docs_root)
    if song_nav:
        _write_pages(docs_root / "松" / ".pages", song_nav)

    print("OK")
    print(f"- Folderized sections: {len(moves)}")
    print(f"- Rewrote markdown files: {rewritten}")
    if song_nav:
        print(f"- Wrote nav: {docs_root / '松' / '.pages'}")


if __name__ == "__main__":
    main()

import argparse
import os
import re
import urllib.parse
from dataclasses import dataclass
from pathlib import Path


HEADING_RE = re.compile(r"^(?P<level>#{1,6})\s+(?P<title>.+?)\s*$")
MD_LINK_RE = re.compile(
    r"(?P<prefix>!?\[[^\]]*\]\()"
    r"(?P<target>(?:[^()\\]|\\.|\([^)]*\))+?)"
    r"(?P<suffix>\))"
)


@dataclass(frozen=True)
class Move:
    old_abs: Path
    new_abs: Path


def _decode_path(s: str) -> str:
    return urllib.parse.unquote(s).replace("\\", "/")


def _quote_link_path(path_str: str) -> str:
    return urllib.parse.quote(path_str, safe="/._-~")


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


def _safe_dirname(title: str) -> str:
    # Keep Chinese punctuation; just avoid path separators.
    return title.replace("/", "-").strip()


def _move_with_assets(old_md: Path, new_md: Path) -> list[Move]:
    moves: list[Move] = []
    new_md.parent.mkdir(parents=True, exist_ok=True)
    if old_md.exists() and old_md.resolve() != new_md.resolve():
        old_md.rename(new_md)
        moves.append(Move(old_abs=old_md.resolve(), new_abs=new_md.resolve()))

    # Notion export asset folder is often next to markdown file with same stem.
    old_asset_dir = old_md.with_suffix("")
    if (
        old_asset_dir.exists()
        and old_asset_dir.is_dir()
        and old_asset_dir != old_md.parent
        and old_asset_dir != new_md.parent
    ):
        new_asset_dir = new_md.with_suffix("")
        new_asset_dir.parent.mkdir(parents=True, exist_ok=True)
        if old_asset_dir.resolve() != new_asset_dir.resolve():
            old_asset_dir.rename(new_asset_dir)
            moves.append(
                Move(old_abs=old_asset_dir.resolve(), new_abs=new_asset_dir.resolve())
            )

    return moves


def _resolve_songshi_target(
    *, docs_root: Path, md_path: Path, song_root: Path, songshi_dir: Path, target: str
) -> Path | None:
    path_part, _, _ = _split_target(target)
    if not path_part or _is_external(path_part):
        return None

    decoded = _decode_path(path_part)
    while decoded.startswith("./"):
        decoded = decoded[2:]

    base_dir = md_path.parent
    candidates: list[Path] = []
    candidates.append((base_dir / decoded).resolve())
    # Notion links often start from docs/松
    candidates.append((song_root / decoded).resolve())
    # Within 松史 pages, links sometimes start with '松史/...'
    if decoded.startswith("松史/"):
        candidates.append((songshi_dir / decoded.removeprefix("松史/")).resolve())

    for c in candidates:
        if c.exists() and c.suffix.lower() == ".md" and songshi_dir in c.parents:
            return c

    # Last resort: locate by filename under 松史.
    filename = Path(decoded).name
    hits = [
        p
        for p in songshi_dir.rglob(filename)
        if p.is_file() and p.suffix.lower() == ".md"
    ]
    if len(hits) == 1:
        return hits[0].resolve()

    # If the page was folderized, foo.md might actually be foo/index.md.
    if filename.lower().endswith(".md"):
        stem = Path(filename).stem
        idx_hits = [
            p
            for p in songshi_dir.rglob(stem)
            if p.is_dir() and (p / "index.md").exists()
        ]
        if len(idx_hits) == 1:
            return (idx_hits[0] / "index.md").resolve()
    return None


def _parse_groups(index_path: Path) -> tuple[list[str], dict[str, list[str]]]:
    skip_h1 = {"松史", "田松大事记"}
    order: list[str] = []
    groups: dict[str, list[str]] = {}
    current: str | None = None

    for line in index_path.read_text(encoding="utf-8").splitlines():
        m = HEADING_RE.match(line.strip())
        if m:
            level = len(m.group("level"))
            title = m.group("title").strip()
            if level == 1:
                if title in skip_h1:
                    current = None
                else:
                    key = title
                    current = key
                    if key not in groups:
                        groups[key] = []
                        order.append(key)
            elif level == 2:
                key = title
                current = key
                if key not in groups:
                    groups[key] = []
                    order.append(key)
            continue

        if current is None:
            continue
        if "](" not in line:
            continue

        for link in MD_LINK_RE.finditer(line):
            groups[current].append(link.group("target").strip())

    return order, groups


def _folderize_pages(songshi_dir: Path) -> list[Move]:
    moves: list[Move] = []
    for md in list(songshi_dir.rglob("*.md")):
        if md.name == "index.md":
            continue
        d = md.with_suffix("")
        if not d.is_dir():
            continue
        if not any(p.is_file() and p.suffix.lower() == ".md" for p in d.rglob("*.md")):
            continue
        new_md = d / "index.md"
        if new_md.exists():
            continue
        md.rename(new_md)
        moves.append(Move(old_abs=md.resolve(), new_abs=new_md.resolve()))
    return moves


def _promote_laobantangmei(songshi_dir: Path) -> list[Move]:
    """Promote 老板堂妹 to same level as 贵大追妹 within 松史.

    Notion export nests 老板堂妹 under 贵大追妹's asset directory. For this repo,
    we want 贵大追妹 and 老板堂妹 as sibling pages.
    """
    moves: list[Move] = []
    for nested_md in songshi_dir.rglob("贵大追妹/老板堂妹.md"):
        parent_dir = nested_md.parent.parent  # .../<group>/
        target_md = parent_dir / "老板堂妹.md"
        if not target_md.exists():
            nested_md.rename(target_md)
            moves.append(Move(old_abs=nested_md.resolve(), new_abs=target_md.resolve()))

        nested_assets = nested_md.with_suffix("")
        target_assets = parent_dir / "老板堂妹"
        if (
            nested_assets.exists()
            and nested_assets.is_dir()
            and not target_assets.exists()
        ):
            nested_assets.rename(target_assets)
            moves.append(
                Move(old_abs=nested_assets.resolve(), new_abs=target_assets.resolve())
            )

    return moves


def _rewrite_links_in_file(
    *,
    md_path: Path,
    docs_root: Path,
    song_root: Path,
    songshi_dir: Path,
    move_map: dict[Path, Path],
) -> bool:
    text = md_path.read_text(encoding="utf-8")
    changed = False

    def repl(m: re.Match[str]) -> str:
        nonlocal changed
        target = m.group("target").strip()
        path_part, query, frag = _split_target(target)
        if not path_part or _is_external(path_part):
            return m.group(0)

        decoded = _decode_path(path_part)
        while decoded.startswith("./"):
            decoded = decoded[2:]

        base_dir = md_path.parent

        # Fast path: already resolves.
        resolved: Path | None = None
        direct = (base_dir / decoded).resolve()
        if direct.exists():
            resolved = direct

        # Special: docs/index.md linking to 松/松史.md
        if resolved is None and decoded.endswith("松/松史.md"):
            alt = (docs_root / "松" / "松史" / "index.md").resolve()
            if alt.exists():
                resolved = alt

        if resolved is None:
            candidates: list[Path] = []
            candidates.append((base_dir / decoded).resolve())
            candidates.append((song_root / decoded).resolve())
            if decoded.startswith("松史/"):
                candidates.append(
                    (songshi_dir / decoded.removeprefix("松史/")).resolve()
                )

            for c in candidates:
                if c.exists():
                    resolved = c
                    break

            if resolved is None:
                for c in candidates:
                    mapped = move_map.get(c)
                    if mapped is None:
                        continue
                    resolved = mapped
                    # Follow chained moves (e.g. foo.md -> dir/foo.md -> dir/foo/index.md)
                    seen: set[Path] = set()
                    while resolved in move_map and resolved not in seen:
                        seen.add(resolved)
                        resolved = move_map[resolved]
                    break

        if resolved is None:
            # For links like '松史/xxx.md' from docs/松/* pages, locate by filename under 松史/.
            if decoded.startswith("松史/") or "松史/" in decoded:
                filename = Path(decoded).name
                hits = [p for p in songshi_dir.rglob(filename) if p.is_file()]
                if len(hits) == 1:
                    resolved = hits[0].resolve()

        if resolved is None:
            # If a link points to foo.md but the page was folderized to foo/index.md, fix it.
            if decoded.lower().endswith(".md"):
                cand = (base_dir / decoded).resolve()
                folder = cand.with_suffix("")
                idx = folder / "index.md"
                if idx.exists():
                    resolved = idx.resolve()

        if resolved is None:
            return m.group(0)

        if not resolved.exists():
            # As a last resort, try filename lookup under 松史.
            filename = resolved.name
            hits = [p for p in songshi_dir.rglob(filename) if p.is_file()]
            if len(hits) == 1:
                resolved = hits[0].resolve()
            else:
                return m.group(0)

        rel = Path(os.path.relpath(resolved, base_dir)).as_posix()
        new_target = _quote_link_path(rel) + query + frag
        if new_target != target:
            changed = True
        return f"{m.group('prefix')}{new_target}{m.group('suffix')}"

    new_text = MD_LINK_RE.sub(repl, text)
    if changed:
        md_path.write_text(new_text, encoding="utf-8")
    return changed


def _write_pages(path: Path, title: str | None, nav: list[str]) -> None:
    lines: list[str] = []
    if title is not None:
        lines.append(f"title: {title}")
    lines.append("nav:")
    for item in nav:
        lines.append(f"  - {item}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Organize docs/松/松史 by headings in docs/松/松史/index.md and fix links."
    )
    parser.add_argument(
        "--docs", type=Path, required=True, help="MkDocs docs/ directory"
    )
    args = parser.parse_args()

    docs_root = args.docs.resolve()
    song_root = docs_root / "松"
    songshi_dir = song_root / "松史"
    songshi_dir.mkdir(parents=True, exist_ok=True)

    # Ensure index exists: if old 松史.md exists, move it.
    songshi_toc = song_root / "松史.md"
    index_path = songshi_dir / "index.md"
    moves: list[Move] = []
    if songshi_toc.exists() and not index_path.exists():
        moves.extend(_move_with_assets(songshi_toc, index_path))
    if not index_path.exists():
        return

    order, groups = _parse_groups(index_path)

    group_dirnames: dict[str, str] = {title: _safe_dirname(title) for title in order}

    # Move markdown files referenced by each group.
    for title in order:
        if not groups.get(title):
            continue
        group_dir = songshi_dir / group_dirnames[title]
        group_dir.mkdir(parents=True, exist_ok=True)
        for t in groups.get(title, []):
            abs_old = _resolve_songshi_target(
                docs_root=docs_root,
                md_path=index_path,
                song_root=song_root,
                songshi_dir=songshi_dir,
                target=t,
            )
            if abs_old is None:
                continue
            if abs_old.resolve() == index_path.resolve():
                continue
            if abs_old.name == "index.md":
                # Already folderized.
                continue
            new_md = (group_dir / abs_old.name).resolve()
            moves.extend(_move_with_assets(abs_old, new_md))

            # If there is a sibling directory with same stem (usually attachments or subpages), move it too.
            sibling_dir = abs_old.parent / abs_old.stem
            if sibling_dir.exists() and sibling_dir.is_dir():
                new_sibling = group_dir / sibling_dir.name
                if sibling_dir.resolve() != new_sibling.resolve():
                    new_sibling.parent.mkdir(parents=True, exist_ok=True)
                    sibling_dir.rename(new_sibling)
                    moves.append(
                        Move(
                            old_abs=sibling_dir.resolve(), new_abs=new_sibling.resolve()
                        )
                    )

    # Special normalization for known bad source nesting.
    moves.extend(_promote_laobantangmei(songshi_dir))

    move_map: dict[Path, Path] = {m.old_abs: m.new_abs for m in moves}

    # Rewrite links across the entire docs/ tree.
    rewritten = 0
    for md in docs_root.rglob("*.md"):
        if _rewrite_links_in_file(
            md_path=md,
            docs_root=docs_root,
            song_root=song_root,
            songshi_dir=songshi_dir,
            move_map=move_map,
        ):
            rewritten += 1

    # Build .pages for sidebar.
    nav_root: list[str] = ["index.md"]
    visible_titles: list[str] = []
    for title in order:
        group_dir = songshi_dir / group_dirnames[title]
        if not group_dir.exists():
            continue
        has_content = any(p.name != ".pages" for p in group_dir.iterdir())
        if not has_content:
            continue
        visible_titles.append(title)
        nav_root.append(group_dirnames[title])
    _write_pages(songshi_dir / ".pages", title="松史", nav=nav_root)

    for title in visible_titles:
        group_dir = songshi_dir / group_dirnames[title]
        nav: list[str] = []
        nav_seen: set[str] = set()
        for t in groups.get(title, []):
            abs_target = _resolve_songshi_target(
                docs_root=docs_root,
                md_path=index_path,
                song_root=song_root,
                songshi_dir=songshi_dir,
                target=t,
            )
            if abs_target is None:
                continue

            # Prefer using the resolved path directly if it lives under this group.
            p: Path | None = None
            try:
                _ = abs_target.relative_to(group_dir)
                p = abs_target
            except ValueError:
                p = None

            if p is None:
                # Fallback: locate by file name (only for non-index pages).
                if abs_target.name != "index.md":
                    hits = [x for x in group_dir.rglob(abs_target.name) if x.is_file()]
                    if len(hits) == 1:
                        p = hits[0]

            if p is None:
                continue

            if p.name == "index.md":
                entry = p.parent.name
                if entry not in nav_seen:
                    nav.append(entry)
                    nav_seen.add(entry)
                continue

            folderized = p.with_suffix("") / "index.md"
            if folderized.exists():
                entry = p.stem
            else:
                entry = p.name
            if entry not in nav_seen:
                nav.append(entry)
                nav_seen.add(entry)

        # Include extra sibling markdown files not listed in index (e.g. 老板堂妹.md).
        extra = sorted(
            x.name
            for x in group_dir.glob("*.md")
            if x.name != "index.md" and x.name not in nav_seen
        )
        nav.extend(extra)
        if nav:
            _write_pages(group_dir / ".pages", title=None, nav=nav)

    print("OK")
    print(f"- Moves: {len(moves)}")
    print(f"- Rewrote markdown files: {rewritten}")


if __name__ == "__main__":
    main()

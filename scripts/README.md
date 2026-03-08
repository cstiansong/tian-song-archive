# Scripts Guide

本目录包含从 Notion 导出重建 `docs/`、链接修复、媒体压缩与校验脚本。

## 一键重建（推荐）

```bash
python scripts/build_docs_from_export.py --src export --dst . --force
```

执行顺序：
1. 从 `export/` 复制顶层索引到 `docs/index.md`
2. 复制 `export/松/` 到 `docs/松/`
3. （可选）压缩图片/视频
4. 清洗 Notion 后缀并重写链接（`rename_and_relink.py`）
5. 规范松一级目录（`organize_song_sections.py`）
6. 规范松史子目录（`organize_songshi.py`）
7. 最终链接归一化（`final_relink.py`）

## 常用参数

- `--compress-media`：压缩图片+视频
- `--compress-images`：只压缩图片
- `--compress-videos`：只压缩视频
- `--compress-preset strict|balanced|archival`：压缩模板（默认 `strict`）
- `--skip-clean` / `--skip-organize-songshi` / `--skip-final-relink`：按需跳过某步

## 增量图片压缩 + 严格校验

```bash
python scripts/compress_new_images_and_validate.py
```

默认行为：
- 仅压缩相对 `HEAD~1` 新增/变更图片（含 untracked）
- 然后执行 `mkdocs build --strict`

全量压缩：

```bash
python scripts/compress_new_images_and_validate.py --all-images
```

## 各脚本职责

- `build_docs_from_export.py`：Notion 导出 -> `docs/` 主流程
- `rename_and_relink.py`：去 Notion 32 位后缀、重命名并重写链接
- `organize_song_sections.py`：`docs/松/*.md` 与同名目录折叠为目录章节
- `organize_songshi.py`：按标题拆分并整理松史结构
- `final_relink.py`：最终链接修复与归一化
- `media_utils.py`：图片压缩/文件体积等复用函数
- `add_entry.py`：新增条目并同步 `.pages` / 索引
- `import_export.py`：从 Notion 导出目录导入到本地 `export/`

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
- 先对新增/变更 Markdown 自动做并列排版（GitHub 兼容 `<p><img width=...>`）
- 规则：2图双列、3图三列、4+图按每行2张
- 仅压缩相对 `HEAD~1` 新增/变更图片（含 untracked）
- 然后执行 `mkdocs build --strict`

全量压缩：

```bash
python scripts/compress_new_images_and_validate.py --all-images
```

常用开关：
- `--skip-gallery-layout`：跳过并列排版
- `--all-markdown`：对 `docs/` 下全部 Markdown 执行并列排版

按单篇文档引用压缩图片：

```bash
python scripts/compress_images_in_md.py --md "docs/松/松史/追求女生的经历/田松的初恋.md"
```

并列格式检查（CI 同款）：

```bash
python scripts/check_gallery_format.py
```

该检查会在以下情况失败：
- 仍存在旧并列格式（`<div...>`、`<img style=...>`、图片表格并列）
- `auto_gallery_layout.py --dry-run` 仍会修改文件（说明尚未归一化）

## 快速新增条目

```bash
python scripts/add_entry.py --dir "docs/松/松史/追求女生的经历" --name "新条目"
```

默认行为：
- 在目标目录创建 `新条目.md`
- 创建同名素材目录 `新条目/`
- 若存在 `.pages`，自动将 `新条目.md` 追加到 `nav:`
- 当目录是 `docs/松/松史/追求女生的经历` 时，自动更新 `docs/松/松史/index.md` 的「追求女生的经历」段落

常用参数：
- `--dry-run`：只预览将执行的操作
- `--force`：当同名 Markdown 已存在时覆盖

## 各脚本职责

- `build_docs_from_export.py`：Notion 导出 -> `docs/` 主流程
- `rename_and_relink.py`：去 Notion 32 位后缀、重命名并重写链接
- `organize_song_sections.py`：`docs/松/*.md` 与同名目录折叠为目录章节
- `organize_songshi.py`：按标题拆分并整理松史结构
- `final_relink.py`：最终链接修复与归一化
- `media_utils.py`：图片压缩/文件体积等复用函数
- `gallery_utils.py`：多图并列排版（`<p><img width=...>`）复用函数
- `auto_gallery_layout.py`：批量执行并列排版
- `compress_images_in_md.py`：按单篇 Markdown 引用压缩图片
- `check_gallery_format.py`：并列格式规范检查（用于 CI）
- `add_entry.py`：新增条目并同步 `.pages` / 索引
- `import_export.py`：从 Notion 导出目录导入到本地 `export/`

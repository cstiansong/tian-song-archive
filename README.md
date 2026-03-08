# 松史（tian-song-archive）

“以人为镜，可以明得失。”

本仓库用于建设 **松史文档档案**：以事件与时间线为主轴，对相关资料进行结构化整理、索引与持续维护，目标是实现内容 **可检索、可引用、可迭代**。

## 项目定位

- **内容定位**：田松相关资料的结构化档案与时间线。
- **呈现方式**：基于 MkDocs Material 构建文档站点。
- **维护原则**：`docs/` 为唯一发布源；导出数据仅用于迁移和重建。

## 仓库结构

- `docs/index.md`：站点首页与总入口（目录顺序以此为准）。
- `docs/松/松史/index.md`：松史主入口。
- `docs/松/`：松史、松典、松录、松论、松百科、观松者、趣事等分栏。
- `scripts/`：迁移、重建、链接修复、媒体压缩与校验脚本（详见 `scripts/README.md`）。
- `.github/workflows/pages.yml`：GitHub Pages 构建配置。

说明：当 `docs/松/` 下存在“同名 Markdown + 同名目录”时，目录作为章节容器，Markdown 作为该章节 `index.md`。

## 快速开始

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

mkdocs serve
```

## 质量校验

提交前建议至少执行以下检查：

```bash
mkdocs build --strict
```

若本次改动包含图片，建议使用增量压缩 + 严格校验：

```bash
python scripts/compress_new_images_and_validate.py
```

补充：
- 默认仅处理相对 `HEAD~1` 的新增/变更图片（包含 untracked）。
- 全量模式：`python scripts/compress_new_images_and_validate.py --all-images`

## 内容维护规范

- 新增内容优先直接编辑 `docs/`。
- 事件类条目建议命名为 `YYYY-MM-DD 事件名.md`。
- 持续更新或素材较多的主题，建议使用目录章节（`<主题>/index.md` + 同目录素材）。
- 新增条目后需同步：
  - 对应目录 `.pages`（侧边栏顺序）；
  - 入口索引（通常为 `docs/松/松史/index.md`）。

## Notion 迁移与重建

Notion 导出数据到 `docs/` 的重建流程、脚本职责和参数说明见：`scripts/README.md`。

常用命令：

```bash
python scripts/build_docs_from_export.py --src export --dst . --force
```

若需同时压缩媒体（图片+视频）：

```bash
python scripts/build_docs_from_export.py --src export --dst . --force --compress-media
```

## 贡献

- 欢迎通过 PR 补充条目、修复错链、完善分类与索引。
- 调整目录结构或顺序时，请保持 `docs/index.md` 与各级 `.pages` 一致。

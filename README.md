# 松史

“以人为镜，可以明得失。”——松史尝试把关于田松的资料做一次系统化的整理与编纂。

本仓库的核心目标是建设 **松史**：以事件与时间线为主轴，尽量完整地保存、归类与串联关键材料，使其可检索、可引用、可持续维护。
（整体理念与分栏体系可参考：`docs/松/新松学概论.md`。）

## 在线阅读

- 本仓库可通过 GitHub Pages 构建为文档站（MkDocs Material）。
- Pages 的构建配置见：`.github/workflows/pages.yml`

## 内容结构

- `docs/index.md`：站点首页/总入口（目录顺序以此为准）
- `docs/松/松史/`：松史（按一级标题拆分子目录，正文入口为 `docs/松/松史/index.md`）
- 其他分栏（松典/松录/松论/松百科/观松者/趣事等）位于 `docs/松/` 下

说明：`docs/松/` 下若存在“同名 md + 同名目录”，会以目录为章节，并将 md 作为 `index.md`（例如 `松典/index.md`）。

## 新增内容说明

日常新增建议直接编辑 `docs/`（把它当成唯一真源），Notion 仅作为素材/备份来源。

最小工作流：
- 选位置：事件类放 `docs/松/`对应分组；
- 命名：事件建议 `YYYY-MM-DD 事件名.md`；如果会持续更新/附图较多，建议用目录章节：`.../<主题>/index.md`
- 更新入口：把新条目链接补到 `docs/松/松史/index.md` 的对应一级标题下
- 更新侧边栏顺序：把新文件/目录加入对应目录的 `.pages`（如 `docs/松/松史/后仙交时期（2021至今）/.pages`）
- 校验发布：本地运行 `mkdocs build --strict`，确保 CI/Pages 也能通过

## 本地预览

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

mkdocs serve
```

严格校验（用于确保 GitHub Actions 也能通过）：

```bash
mkdocs build --strict
```

## 从 Notion 重新导出后更新

Notion 迁移/重建 `docs/` 的具体流程与脚本说明放在 `scripts/`（本 README 不展开）。

常用命令：

```bash
python scripts/build_docs_from_export.py --src export --dst . --force
```

提示：
- `export/` 仅作为本地备份（默认不提交，见 `.gitignore`）
- 对外的是 `docs/`


## 贡献与修订

- 欢迎以 PR 的方式补充松史条目、修复错链、完善分类与索引。
- 若需调整目录顺序，请优先修改/保持 `docs/index.md` 的顺序一致性。

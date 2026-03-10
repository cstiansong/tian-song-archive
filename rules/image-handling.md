# 图片处理规则

## 多图并列格式（统一）

使用 GitHub 兼容写法：

```html
<p>
  <img src="a.png" alt="a" width="49%">
  <img src="b.png" alt="b" width="49%">
</p>
```

规则：

- 2 图：`width="49%"`
- 3 图：`width="32%"`
- 4 图及以上：按每行 2 图分组

## 引用路径规则

- 多图并列中的 `<img src>` 优先使用同目录相对文件名。
- 单图 `![...](...)` 可沿用仓库现有 URL 编码路径风格。
- 禁止引用不存在文件；图片必须先复制到目标目录。

## 压缩规则

- 默认参数：`max_width=1400`、`jpg_quality=68`。
- 同一批图片避免反复压缩（有损压缩会持续降质）。

按单篇文档引用压缩：

```bash
python scripts/compress_images_in_md.py --md "docs/松/松史/追求女生的经历/田松的初恋.md"
```

增量压缩 + 校验：

```bash
python scripts/compress_new_images_and_validate.py
```

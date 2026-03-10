# 提交前校验门禁

## 本地最小校验

```bash
python scripts/check_gallery_format.py
mkdocs build --strict
```

## 推荐一键校验

```bash
python scripts/compress_new_images_and_validate.py
```

该命令会按顺序执行：

1. 新增/变更 Markdown 的多图并列规范化
2. 新增/变更图片压缩
3. 并列格式规范检查
4. `mkdocs build --strict`

## CI 对齐

CI（`pages.yml`）应至少包含：

- `python scripts/check_gallery_format.py`
- `mkdocs build --strict`

本地通过上述检查后再提交，可显著降低 CI 失败概率。

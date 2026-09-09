# -*- coding: utf-8 -*-
"""向量重建 CLI（薄壳，核心逻辑在 app.service.vector_rebuild_service）。

适用场景：Milvus 数据卷重置/丢失 → MySQL 有 chunk 记录但 Milvus 没向量（6.5 对账补偿）。
纯增量、无删除：源文件与 MySQL 记录零影响。

用法：
    conda activate rag_kb
    python scripts/rebuild_vectors.py            # 全量重建
    python scripts/rebuild_vectors.py --doc-id 2 # 只重建某篇文档
"""

import argparse

from app.service.vector_rebuild_service import rebuild_all, rebuild_documents


def main() -> None:
    parser = argparse.ArgumentParser(description="向量重建工具（对账+补偿）")
    parser.add_argument("--doc-id", type=int, default=None, help="只重建指定文档")
    args = parser.parse_args()

    if args.doc_id is not None:
        n = rebuild_documents([args.doc_id])
        print(f"✅ 重建完成: {n} 条向量已写入 Milvus（doc_id={args.doc_id}）")
    else:
        result = rebuild_all()
        print(
            f"✅ 全量重建完成: {result['chunks']} 条向量已写入 Milvus"
            f"（涉及文档 {result['docs']}）"
        )


if __name__ == "__main__":
    main()

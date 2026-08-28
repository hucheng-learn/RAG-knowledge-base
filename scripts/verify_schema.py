# -*- coding: utf-8 -*-
"""比对 ORM 模型列 与 实际数据库列，确认对齐。"""
from app.models.orm import Base, get_engine

import pymysql
import sqlalchemy

# 用 SQLAlchemy 反射实际库的表结构
insp = sqlalchemy.inspect(get_engine())

db = "rag_knowledge"
conn = pymysql.connect(host="127.0.0.1", port=3306, user="root",
                       password="123456", database=db, charset="utf8mb4")
cur = conn.cursor()

all_ok = True
for table in ["knowledge_bases", "documents", "chunks"]:
    # ORM 列
    orm_cols = set(Base.metadata.tables[table].columns.keys())
    # 实际库列
    cur.execute(
        "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s", (db, table),
    )
    db_cols = {r[0] for r in cur.fetchall()}

    only_orm = orm_cols - db_cols
    only_db = db_cols - orm_cols
    print(f"\n=== {table} ===")
    print(f"  ORM 列数={len(orm_cols)}  DB 列数={len(db_cols)}")
    if only_orm:
        print(f"  仅 ORM 有(DB缺): {only_orm}")
        all_ok = False
    if only_db:
        print(f"  仅 DB 有(ORM缺): {only_db}")
        all_ok = False
    if not only_orm and not only_db:
        print("  ✅ 列完全一致")

conn.close()
print("\n结论:", "✅ ORM 与数据库已对齐" if all_ok else "❌ 仍有差异")

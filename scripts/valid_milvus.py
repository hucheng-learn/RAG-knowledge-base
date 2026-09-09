from pymilvus import MilvusClient

client = MilvusClient(uri="http://127.0.0.1:19530")

# 1. 看 collection 是否存在
print("collections:", client.list_collections())

# 2. 看有多少条向量
stats = client.get_collection_stats("doc_chunks")
print("向量总数:", stats.get("row_count", 0))

# 3. 查具体数据（按 doc_id 过滤）
results = client.query(
    collection_name="doc_chunks",
    # filter="doc_id == 7",  # 换成你 documents 表里的实际 id
    output_fields=["id", "doc_id", "chunk_index", "page_number"],
    limit=100
)
for r in results:
    print(r)
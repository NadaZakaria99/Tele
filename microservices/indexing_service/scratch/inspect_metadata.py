from pymilvus import connections, Collection
import json

def check_metadata():
    connections.connect("default", host="milvus", port="19530")
    col = Collection("nbe_documents")
    col.load()
    res = col.query(expr='chunk_id != ""', output_fields=["bbox", "doc_id", "chunk_id"], limit=5)
    for row in res:
        print(f"Chunk: {row['chunk_id']}")
        print(f"Bbox: {row['bbox']}")
        print(f"Doc: {row['doc_id']}")
        print("-" * 20)

if __name__ == "__main__":
    check_metadata()

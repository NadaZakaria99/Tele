from pymilvus import connections, Collection
import numpy as np

def test_search():
    connections.connect("default", host="milvus", port="19530")
    col = Collection("nbe_documents")
    col.load()
    
    print(f"Entities (num_entities): {col.num_entities}")
    
    # Try a search with a dummy vector
    search_params = {"metric_type": "L2", "params": {"nprobe": 10}}
    dummy_vector = [0.0] * 2048
    
    results = col.search(
        data=[dummy_vector],
        anns_field="embedding",
        param=search_params,
        limit=5,
        output_fields=["doc_id", "text"]
    )
    
    print("Search Results:")
    for hit in results[0]:
        print(f" - Doc: {hit.entity.get('doc_id')}, Score: {hit.distance}")
        print(f"   Text: {hit.entity.get('text')[:100]}...")

if __name__ == "__main__":
    test_search()

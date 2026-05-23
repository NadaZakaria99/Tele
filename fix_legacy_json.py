import os
import json
import glob

def fix_json_file(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    modified = False
    
    # 1. Add inference_size if missing
    if 'inference_size' not in data:
        data['inference_size'] = data.get('original_size', [2000, 2000])
        modified = True
        
    # 2. Convert bbox lists to dicts
    if 'blocks' in data:
        for block in data['blocks']:
            if 'bbox' in block and isinstance(block['bbox'], list):
                bbox_list = block['bbox']
                if len(bbox_list) == 4:
                    block['bbox'] = {
                        "x1": round(bbox_list[0]),
                        "y1": round(bbox_list[1]),
                        "x2": round(bbox_list[2]),
                        "y2": round(bbox_list[3])
                    }
                    modified = True
                    
    if modified:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"Fixed: {file_path}")

def main():
    base_dir = "/home/asoliman/projects/nbe-knowledge-assistant/data/legacy/pipeline_output/extractions"
    json_files = glob.glob(os.path.join(base_dir, "**", "*.json"), recursive=True)
    
    print(f"Found {len(json_files)} JSON files. Fixing...")
    for fp in json_files:
        fix_json_file(fp)
    print("Done!")

if __name__ == '__main__':
    main()

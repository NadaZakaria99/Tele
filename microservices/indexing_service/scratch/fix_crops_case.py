import os
from pathlib import Path

def fix_crops_case(extractions_dir):
    for json_file in Path(extractions_dir).rglob("*.json"):
        with open(json_file, "r", encoding="utf-8") as f:
            content = f.read()
        
        new_content = content.replace('"Crops/', '"crops/')
        
        if new_content != content:
            with open(json_file, "w", encoding="utf-8") as f:
                f.write(new_content)
            print(f"Fixed {json_file}")

if __name__ == "__main__":
    fix_crops_case("/home/asoliman/projects/nbe-knowledge-assistant/data/legacy/pipeline_output/extractions")

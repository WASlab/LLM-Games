# export.py
import os
import json

def collect_python_files(root_dir: str) -> dict:
    file_structure = {}

    for dirpath, _, filenames in os.walk(root_dir):
        for file in filenames:
            if file.endswith('.py'):
                full_path = os.path.join(dirpath, file)
                rel_path = os.path.relpath(full_path, root_dir)
                with open(full_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                file_structure[rel_path] = content

    return file_structure

def export_to_json(output_path="code_snapshot.json", root="mafia"):
    all_files = collect_python_files(root)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(all_files, f, indent=2)

def export_to_text(output_path="code_snapshot.txt", root="llm_games"):
    all_files = collect_python_files(root)
    with open(output_path, 'w', encoding='utf-8') as f:
        for path, content in all_files.items():
            f.write(f"# === {path} ===\n")
            f.write(content + "\n\n")

if __name__ == "__main__":
    export_to_json()
    export_to_text()
    print("✅ Codebase exported to 'code_snapshot.json' and 'code_snapshot.txt'")

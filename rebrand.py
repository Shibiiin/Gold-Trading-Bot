import os

def replace_in_file(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return # Skip binary or unreadable files

    new_content = content
    # Order matters: replace longer strings first
    replacements = {
        "Gold-Trading-Bot": "Gold-Trading-Bot",
        "Gold-Bot": "Gold-Bot",
        "llm_adapter": "llm_adapter",
        "run_bot": "run_bot",
        "GoldBotEA": "GoldBotEA",
        "GoldBot": "GoldBot",
        "goldbot": "goldbot",
        "Gold Bot": "Gold Bot",
        "Goldbot": "Goldbot",
        "GOLDBOT": "GOLDBOT"
    }
    
    changed = False
    for old_str, new_str in replacements.items():
        if old_str in new_content:
            new_content = new_content.replace(old_str, new_str)
            changed = True
            
    if changed:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"Updated content in: {filepath}")

def main():
    root_dir = '/Users/shibinm/Desktop/miro-fish/Gold-Trading-Bot'
    
    # 1. Rename files first
    renames = [
        ("run_bot.py", "run_bot.py"),
        ("goldbot_backend_stub.py", "llm_backend_stub.py"),
        ("trading/GoldBotEA.mq5", "trading/GoldBotEA.mq5"),
        ("trading/llm_adapter.py", "trading/llm_adapter.py")
    ]
    
    for old_name, new_name in renames:
        old_path = os.path.join(root_dir, old_name)
        new_path = os.path.join(root_dir, new_name)
        if os.path.exists(old_path):
            os.rename(old_path, new_path)
            print(f"Renamed file: {old_name} -> {new_name}")

    # 2. Walk directories and update content
    for dirpath, dirnames, filenames in os.walk(root_dir):
        # skip git and node_modules and venv
        if '.git' in dirpath or 'node_modules' in dirpath or '.venv' in dirpath or '__pycache__' in dirpath or 'dist' in dirpath:
            continue
            
        for filename in filenames:
            if filename.endswith(('.py', '.js', '.vue', '.md', '.json', '.html', '.css', '.mq5', '.txt', '.toml', '.yml', '.env.example')):
                filepath = os.path.join(dirpath, filename)
                replace_in_file(filepath)

if __name__ == "__main__":
    main()
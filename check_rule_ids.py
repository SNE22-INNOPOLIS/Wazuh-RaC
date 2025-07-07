import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
import sys

def run_git_command(args):
    result = subprocess.run(args, capture_output=True, text=True, check=True)
    return result.stdout

def get_changed_rule_files():
    """Get list of changed (A or M) rule files and their status."""
    try:
        output = run_git_command(["git", "diff", "--name-status", "origin/main...HEAD"])
        changed_files = []
        for line in output.splitlines():
            status, file_path = line.split(maxsplit=1)
            if file_path.startswith("rules/") and file_path.endswith(".xml"):
                changed_files.append((status, Path(file_path)))
        return changed_files
    except subprocess.CalledProcessError as e:
        print("❌ Failed to get changed files:", e)
        sys.exit(1)

def extract_rule_ids_from_xml(content):
    ids = set()
    try:
        root = ET.fromstring(content)
        for rule in root.findall(".//rule"):
            rule_id = rule.get("id")
            if rule_id and rule_id.isdigit():
                ids.add(int(rule_id))
    except ET.ParseError:
        pass
    return ids

def get_all_main_rule_ids():
    """Extract rule IDs from all rule files in origin/main."""
    run_git_command(["git", "fetch", "origin", "main"])
    files_output = run_git_command(["git", "ls-tree", "-r", "origin/main", "--name-only"])
    xml_files = [f for f in files_output.splitlines() if f.startswith("rules/") and f.endswith(".xml")]

    all_ids = set()
    for file in xml_files:
        content = run_git_command(["git", "show", f"origin/main:{file}"])
        all_ids.update(extract_rule_ids_from_xml(content))
    return all_ids

def get_rule_ids_from_main_version(file_path: Path):
    try:
        content = run_git_command(["git", "show", f"origin/main:{file_path}"])
        return extract_rule_ids_from_xml(content)
    except subprocess.CalledProcessError:
        return set()  # file doesn't exist in main

def main():
    changed_files = get_changed_rule_files()
    if not changed_files:
        print("✅ No rule files were changed in this PR.")
        return

    print(f"🔍 Checking rule ID conflicts for files: {[f.name for _, f in changed_files]}")
    all_main_ids = get_all_main_rule_ids()

    for status, path in changed_files:
        print(f"\n🔎 Checking file: {path.name}")

        try:
            dev_content = path.read_text()
            dev_ids = extract_rule_ids_from_xml(dev_content)
        except Exception as e:
            print(f"⚠️ Could not read {path.name}: {e}")
            continue

        if status == "A":
            # New file — check all IDs for conflicts
            conflicts = dev_ids & all_main_ids
            if conflicts:
                print(f"❌ Conflict in new file {path.name}. Rule IDs: {sorted(conflicts)}")
                sys.exit(1)
            else:
                print(f"✅ No conflict in new file {path.name}")

        elif status == "M":
            # Existing file — compare its current and main branch version
            main_ids = get_rule_ids_from_main_version(path)

            if dev_ids == main_ids:
                print(f"ℹ️ {path.name} modified but rule IDs unchanged.")
                continue  # Safe
            else:
                new_ids = dev_ids - main_ids  # Only new or changed IDs
                conflicts = new_ids & (all_main_ids - main_ids)
                if conflicts:
                    print(f"❌ Conflict in modified file {path.name}. New rule IDs conflicting: {sorted(conflicts)}")
                    sys.exit(1)
                else:
                    print(f"✅ Modified file {path.name} has no conflicting new rule IDs.")

    print("\n✅ All rule file changes passed conflict checks.")

if __name__ == "__main__":
    main()

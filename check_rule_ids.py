import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
import sys
from collections import Counter, defaultdict

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
    ids = []
    try:
        root = ET.fromstring(content)
        for rule in root.findall(".//rule"):
            rule_id = rule.get("id")
            if rule_id and rule_id.isdigit():
                ids.append(int(rule_id))
    except ET.ParseError:
        pass
    return ids

def get_rule_ids_per_file_main(exclude_file=None):
    """Returns a dict mapping each rule ID to the file(s) it appears in on origin/main."""
    run_git_command(["git", "fetch", "origin", "main"])
    files_output = run_git_command(["git", "ls-tree", "-r", "origin/main", "--name-only"])
    xml_files = [f for f in files_output.splitlines() if f.startswith("rules/") and f.endswith(".xml")]

    rule_id_to_files = defaultdict(set)
    for file in xml_files:
        if exclude_file and file == exclude_file.as_posix():
            continue
        try:
            content = run_git_command(["git", "show", f"origin/main:{file}"])
            rule_ids = extract_rule_ids_from_xml(content)
            for rule_id in rule_ids:
                rule_id_to_files[rule_id].add(file)
        except subprocess.CalledProcessError:
            continue
    return rule_id_to_files

def get_rule_ids_from_main_version(file_path: Path):
    try:
        content = run_git_command(["git", "show", f"origin/main:{file_path}"])
        return extract_rule_ids_from_xml(content)
    except subprocess.CalledProcessError:
        return []

def detect_duplicates(rule_ids):
    counter = Counter(rule_ids)
    return [rule_id for rule_id, count in counter.items() if count > 1]

def print_conflicts(conflicting_ids, rule_id_to_files):
    print("❌ Conflicts detected:")
    for rule_id in sorted(conflicting_ids):
        files = rule_id_to_files.get(rule_id, [])
        print(f"  - Rule ID {rule_id} found in:")
        for f in files:
            print(f"    • {f}")

def main():
    changed_files = get_changed_rule_files()
    if not changed_files:
        print("✅ No rule files were changed in this PR.")
        return

    print(f"🔍 Checking rule ID conflicts for files: {[f.name for _, f in changed_files]}")

    for status, path in changed_files:
        print(f"\n🔎 Checking file: {path.name}")

        try:
            dev_content = path.read_text()
            dev_ids = extract_rule_ids_from_xml(dev_content)
        except Exception as e:
            print(f"⚠️ Could not read {path.name}: {e}")
            continue

        # Detect duplicates in the same file
        duplicates = detect_duplicates(dev_ids)
        if duplicates:
            print(f"❌ Duplicate rule IDs detected in {path.name}: {sorted(duplicates)}")
            sys.exit(1)

        rule_id_to_files = get_rule_ids_per_file_main(exclude_file=path if status == "M" else None)

        if status == "A":
            conflicting_ids = set(dev_ids) & set(rule_id_to_files.keys())
            if conflicting_ids:
                print_conflicts(conflicting_ids, rule_id_to_files)
                sys.exit(1)
            else:
                print(f"✅ No conflict in new file {path.name}")

        elif status == "M":
            main_ids = get_rule_ids_from_main_version(path)

            if set(dev_ids) == set(main_ids):
                print(f"ℹ️ {path.name} modified but rule IDs unchanged.")
                continue

            new_or_changed_ids = set(dev_ids) - set(main_ids)
            conflicting_ids = new_or_changed_ids & set(rule_id_to_files.keys())
            if conflicting_ids:
                print_conflicts(conflicting_ids, rule_id_to_files)
                sys.exit(1)
            else:
                print(f"✅ Modified file {path.name} has no conflicting rule IDs.")

    print("\n✅ All rule file changes passed conflict checks.")

if __name__ == "__main__":
    main()

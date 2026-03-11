#!/usr/bin/env python3
"""
sync_skills.py — Auto-sync Jarvis workspace skills → Herkulio intelligence knowledge base.

Any workspace skill tagged as OSINT/research/intelligence relevant gets
distilled into Herkulio's skills directory as investigation playbooks.

Run: python3 sync_skills.py
     python3 sync_skills.py --list     (show what would sync)
     python3 sync_skills.py --force    (re-sync all, overwrite existing)
"""
import os, sys, json, time

WORKSPACE_SKILLS = "/home/jarvis/.openclaw/workspace/skills"
HERKULIO_SKILLS  = "/home/jarvis/.openclaw/workspace/osint/herkulio/skills"

# Skills to sync and their target Herkulio skill name
# Format: "workspace_skill_name": "herkulio_skill_name"
SYNC_MAP = {
    "watch-osint":              "watch-osint",
    "social-media-scraper":     "social-media-osint",
    "deep-research-pro":        "deep-research",
    "in-depth-research":        "deep-research",
    "research":                 "deep-research",
    "financial-analyst":        "financial-osint",
    "market-research":          "financial-osint",
    "data-analysis":            "financial-osint",
    "afrexai-web-scraping-engine": "web-intelligence",
    "intelligence-suite":       "universal-intel",
    "crm-in-a-box":             None,  # skip — not OSINT relevant
    "automation-workflows":     None,  # skip
    "blog-image-generator":     None,  # skip
    "instagram-slides":         None,  # skip
    "talking-head":             None,  # skip
    "elevenlabs-calls":         None,  # skip
    "x-posting":                None,  # skip
    "telegram-bot":             None,  # skip
    "trading-devbox":           None,  # skip
    "revenue-metrics":          None,  # skip
}

SYNC_LOG = "/home/jarvis/.openclaw/workspace/osint/herkulio/skills/.sync_log.json"

def load_log():
    try:
        return json.load(open(SYNC_LOG))
    except Exception:
        return {}

def save_log(log):
    os.makedirs(os.path.dirname(SYNC_LOG), exist_ok=True)
    json.dump(log, open(SYNC_LOG, "w"), indent=2)

def get_skill_mtime(skill_name):
    skill_dir = os.path.join(WORKSPACE_SKILLS, skill_name)
    skill_md  = os.path.join(skill_dir, "SKILL.md")
    try:
        return os.path.getmtime(skill_md)
    except Exception:
        return 0

def sync_skill(workspace_skill, herkulio_skill, force=False):
    """Copy SKILL.md content into Herkulio's references directory."""
    src = os.path.join(WORKSPACE_SKILLS, workspace_skill, "SKILL.md")
    if not os.path.exists(src):
        return False, "source not found"

    dst_dir = os.path.join(HERKULIO_SKILLS, herkulio_skill, "references")
    os.makedirs(dst_dir, exist_ok=True)

    # Target filename based on workspace skill name
    dst_file = os.path.join(dst_dir, f"synced-{workspace_skill}.md")

    # Check if sync needed
    log = load_log()
    src_mtime = get_skill_mtime(workspace_skill)
    log_key = f"{workspace_skill}->{herkulio_skill}"

    if not force and log.get(log_key, {}).get("mtime") == src_mtime:
        return False, "up to date"

    # Read source, strip YAML frontmatter, write as intelligence reference
    content = open(src).read()
    # Strip YAML frontmatter (between --- markers)
    if content.startswith("---"):
        end = content.find("---", 3)
        if end > 0:
            content = content[end+3:].strip()

    # Add header
    output = f"# Intelligence Reference: {workspace_skill.replace('-', ' ').title()}\n"
    output += f"*Synced from workspace skill: {workspace_skill}*\n\n"
    output += content

    open(dst_file, "w").write(output)

    # Update log
    log[log_key] = {
        "mtime": src_mtime,
        "synced_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "dst": dst_file,
    }
    save_log(log)

    return True, "synced"

def main():
    force = "--force" in sys.argv
    list_only = "--list" in sys.argv

    print("Herkulio Skills Sync")
    print("=" * 40)

    synced = 0
    skipped = 0
    errors = 0

    for workspace_skill, herkulio_skill in sorted(SYNC_MAP.items()):
        if herkulio_skill is None:
            if list_only:
                print(f"  SKIP  {workspace_skill} (not OSINT relevant)")
            continue

        src = os.path.join(WORKSPACE_SKILLS, workspace_skill, "SKILL.md")
        if not os.path.exists(src):
            if list_only:
                print(f"  MISS  {workspace_skill} → {herkulio_skill} (not installed)")
            continue

        if list_only:
            print(f"  SYNC  {workspace_skill} → {herkulio_skill}")
            continue

        ok, reason = sync_skill(workspace_skill, herkulio_skill, force=force)
        if ok:
            print(f"  ✅  {workspace_skill} → {herkulio_skill}")
            synced += 1
        elif reason == "up to date":
            skipped += 1
        else:
            print(f"  ❌  {workspace_skill}: {reason}")
            errors += 1

    # Auto-discover workspace skills not in the map
    if os.path.exists(WORKSPACE_SKILLS):
        for skill in sorted(os.listdir(WORKSPACE_SKILLS)):
            if skill not in SYNC_MAP:
                # Auto-classify by name
                osint_keywords = ["osint","research","intel","scraper","scraping",
                                  "data","financial","market","analysis","monitor",
                                  "watch","track","price","competitor","news"]
                if any(kw in skill.lower() for kw in osint_keywords):
                    if list_only:
                        print(f"  AUTO  {skill} → universal-intel (auto-detected)")
                    elif not force:
                        pass  # don't auto-sync without explicit mapping
                    else:
                        ok, reason = sync_skill(skill, "universal-intel", force=force)
                        if ok:
                            print(f"  ✅  AUTO {skill} → universal-intel")
                            synced += 1

    if not list_only:
        print("=" * 40)
        print(f"Synced: {synced} | Skipped (up to date): {skipped} | Errors: {errors}")
        print("Restart the Herkulio bot to load new knowledge.")

if __name__ == "__main__":
    main()

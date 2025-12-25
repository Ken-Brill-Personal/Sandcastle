#!/usr/bin/env python3
"""
Reactivate Automations

Author: Ken Brill
Version: 1.0
Date: December 24, 2025
License: MIT License
"""

import json
import subprocess
from pathlib import Path

# Get script directory to find config.json
script_dir = Path(__file__).parent
config_path = script_dir / "config.json"

# Load config to get target org alias and project directory
with open(config_path) as f:
    config = json.load(f)
    ORG_ALIAS = config.get("target_sandbox_alias")
    if not ORG_ALIAS:
        print("Error: target_sandbox_alias not found in config.json")
        exit(1)
    
    sfdx_project_dir = config.get("sfdx_project_dir", "../KBRILL")
    PROJECT_DIR = (script_dir / sfdx_project_dir).resolve()
    if not PROJECT_DIR.exists():
        print(f"Error: SFDX project directory not found: {PROJECT_DIR}")
        exit(1)

print(f"Target org: {ORG_ALIAS}")
print(f"Project dir: {PROJECT_DIR}\n")

STATE_FILE = script_dir / "sf_disabled_state.json"

def run(cmd, cwd=None):
    print(">", " ".join(cmd))
    return subprocess.check_output(cmd, text=True, cwd=cwd)

with open(STATE_FILE) as f:
    state = json.load(f)

# -------------------------------------------------
# FLOWS
# -------------------------------------------------
for flow_file in (PROJECT_DIR / "force-app").rglob("*.flow-meta.xml"):
    for f in state["flows"]:
        if f["name"] in flow_file.name:
            text = flow_file.read_text()
            text = text.replace("<status>Draft</status>", "<status>Active</status>")
            flow_file.write_text(text)

# -------------------------------------------------
# TRIGGERS
# -------------------------------------------------
for trigger_file in (PROJECT_DIR / "force-app").rglob("*.trigger-meta.xml"):
    for t in state["triggers"]:
        if t in trigger_file.name:
            text = trigger_file.read_text()
            text = text.replace("<status>Inactive</status>", "<status>Active</status>")
            trigger_file.write_text(text)

run([
    "sf", "project", "deploy", "start",
    "--source-dir", "force-app",
    "--ignore-conflicts",
    "--target-org", ORG_ALIAS
], cwd=PROJECT_DIR)

print("\n✅ Reactivation complete")

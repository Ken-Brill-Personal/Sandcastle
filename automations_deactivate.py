#!/usr/bin/env python3
"""
Deactivate Automations

Author: Ken Brill
Version: 1.0
Date: December 24, 2025
License: MIT License
"""

import json
import subprocess
import os
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
TMP_DIR = script_dir / "tmp_metadata"
TMP_DIR.mkdir(exist_ok=True)

state = {
    "flows": [],
    "triggers": []
}

def run(cmd, cwd=None):
    print(">", " ".join(cmd))
    result = subprocess.run(cmd, text=True, cwd=cwd, capture_output=True)
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr)
        raise subprocess.CalledProcessError(result.returncode, cmd, result.stdout, result.stderr)
    return result.stdout

# -------------------------------------------------
# FLOWS
# -------------------------------------------------
print("Fetching active flows...")

flows = run([
    "sf", "data", "query",
    "--query",
    "SELECT Definition.DeveloperName, VersionNumber "
    "FROM Flow WHERE Status = 'Active'",
    "--use-tooling-api",
    "--json",
    "--target-org", ORG_ALIAS
])

flows_json = json.loads(flows)
for rec in flows_json["result"]["records"]:
    state["flows"].append({
        "name": rec["Definition"]["DeveloperName"],
        "version": rec["VersionNumber"]
    })

# Pull flow metadata
run([
    "sf", "project", "retrieve", "start",
    "--metadata", "Flow",
    "--ignore-conflicts",
    "--target-org", ORG_ALIAS
], cwd=PROJECT_DIR)

# Deactivate flows by editing XML
for flow_file in (PROJECT_DIR / "force-app").rglob("*.flow-meta.xml"):
    text = flow_file.read_text()
    if "<status>Active</status>" in text:
        text = text.replace("<status>Active</status>", "<status>Draft</status>")
        flow_file.write_text(text)

run([
    "sf", "project", "deploy", "start",
    "--source-dir", "force-app",
    "--ignore-conflicts",
    "--target-org", ORG_ALIAS
], cwd=PROJECT_DIR)

# -------------------------------------------------
# APEX TRIGGERS
# -------------------------------------------------
print("Fetching active Apex triggers...")

triggers = run([
    "sf", "data", "query",
    "--query",
    "SELECT Name FROM ApexTrigger WHERE Status = 'Active'",
    "--json",
    "--target-org", ORG_ALIAS
])

triggers_json = json.loads(triggers)
for rec in triggers_json["result"]["records"]:
    state["triggers"].append(rec["Name"])

run([
    "sf", "project", "retrieve", "start",
    "--metadata", "ApexTrigger",
    "--ignore-conflicts",
    "--target-org", ORG_ALIAS
], cwd=PROJECT_DIR)

for trigger_file in (PROJECT_DIR / "force-app").rglob("*.trigger-meta.xml"):
    text = trigger_file.read_text()
    if "<status>Active</status>" in text:
        text = text.replace("<status>Active</status>", "<status>Inactive</status>")
        trigger_file.write_text(text)

run([
    "sf", "project", "deploy", "start",
    "--source-dir", "force-app",
    "--ignore-conflicts",
    "--target-org", ORG_ALIAS
], cwd=PROJECT_DIR)

# -------------------------------------------------
# SAVE STATE
# -------------------------------------------------
with open(STATE_FILE, "w") as f:
    json.dump(state, f, indent=2)

print("\n✅ Deactivation complete")
print(f"State saved to {STATE_FILE}")

#!/usr/bin/env python3
"""Nexus Demo Script — Run all pipeline stages in sequence."""
import subprocess, sys, os

os.environ.setdefault("GEMINI_API_KEY", "AIzaSyAUFtgY1YrsqXhR7jhwh59QBP3g18DJdxQ")

scripts = [
    ("Build nexus_data.json", "build_nexus_data.py"),
    ("Run Decay Monitor", "decay_monitor.py"),
    ("Run Counterfactual Engine", "counterfactual_engine.py"),
    ("Run Knowledge Concentration", "knowledge_concentration.py"),
    ("Generate Risk Report", "generate_risk_report.py"),
]

for name, script in scripts:
    print(f"\n{'='*60}")
    print(f"  Running: {name}")
    print(f"{'='*60}")
    result = subprocess.run([sys.executable, script], cwd=os.path.dirname(__file__))
    if result.returncode != 0:
        print(f"  [!] {name} failed with exit code {result.returncode}")
    else:
        print(f"  [+] {name} completed successfully")

print(f"\n{'='*60}")
print("  All pipeline stages complete!")
print("  Start API: uvicorn api:app --host 0.0.0.0 --port 8000")
print(f"{'='*60}")

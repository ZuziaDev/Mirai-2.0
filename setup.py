import subprocess
import sys

print("Installing MIRAI Core Dependencies...")
subprocess.run([sys.executable, "-m", "pip", "install", "-r", "deps.txt"], check=True)

print("Initializing Neural Vision (Playwright)...")
subprocess.run([sys.executable, "-m", "playwright", "install"], check=True)

print("\n" + "="*40)
print("✅ MIRAI INFRASTRUCTURE READY")
print("🚀 COMMAND: python igniter.py")
print("="*40 + "\n")

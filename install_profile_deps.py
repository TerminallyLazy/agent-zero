#!/usr/bin/env python3
"""
Install dependencies needed for the profile management system
"""
import subprocess
import sys

dependencies = [
    "flask",
    "flask-basicauth", 
    "openai",
    "playwright",
    "litellm",
    "langchain-core",
    "langchain-community",
    "sentence-transformers",
    "torch",
    "cryptography",
    "openai-whisper",
    "webcolors",
    "gitpython",
    "nest_asyncio",
    "faiss-cpu",
    "pytz",
    "pathspec",
    "python-crontab",
    "simpleeval"
]

def install_package(package):
    """Install a single package"""
    try:
        print(f"Installing {package}...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])
        print(f"✅ {package} installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install {package}: {e}")
        return False

def main():
    print("Installing Profile Management Dependencies...")
    print(f"Found {len(dependencies)} packages to install")
    
    failed = []
    succeeded = []
    
    for dep in dependencies:
        if install_package(dep):
            succeeded.append(dep)
        else:
            failed.append(dep)
    
    print(f"\n✅ Successfully installed: {len(succeeded)} packages")
    print(f"❌ Failed to install: {len(failed)} packages")
    
    if failed:
        print("\nFailed packages:")
        for pkg in failed:
            print(f"  - {pkg}")
        return 1
    else:
        print("\n🎉 All dependencies installed successfully!")
        return 0

if __name__ == "__main__":
    sys.exit(main())
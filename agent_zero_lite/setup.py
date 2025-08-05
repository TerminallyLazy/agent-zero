from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = fh.read().splitlines()

setup(
    name="agent_zero_lite",
    version="0.1.0",
    author="Agent Zero Team",
    author_email="info@agent-zero.ai",
    description="A lightweight implementation of Agent Zero",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/agent-zero-ai/agent-zero-lite",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.9",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "agent-zero-lite=run:main",
        ],
    },
)
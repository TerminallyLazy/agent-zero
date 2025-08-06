#!/usr/bin/env python3
"""
Agent Zero Lite - Lightweight Python AI Agent Framework
"""

from setuptools import setup, find_packages
import os

# Read the contents of requirements.txt
def read_requirements():
    with open('requirements.txt', 'r') as f:
        return [line.strip() for line in f if line.strip() and not line.startswith('#')]

# Read the contents of README.md
def read_readme():
    with open('README.md', 'r', encoding='utf-8') as f:
        return f.read()

setup(
    name="agent-zero-lite",
    version="1.0.12",
    author="Agent Zero Community",
    author_email="support@agent-zero.io",
    description="Lightweight Python AI Agent Framework with Web UI",
    long_description=read_readme(),
    long_description_content_type="text/markdown",
    url="https://github.com/frdel/agent-zero-lite",
    packages=find_packages(include=['agent_zero_lite', 'agent_zero_lite.*']),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    python_requires=">=3.8",
    install_requires=read_requirements(),
    include_package_data=True,
    package_data={
        'agent_zero_lite': [
            'webui/**/*',
            'prompts/**/*',
            'knowledge/**/*',
            'conf/**/*',
            'python/**/*',
            '.env.example',
        ],
    },
    entry_points={
        'console_scripts': [
            'agent-zero-lite=agent_zero_lite.cli:main',
            'azl=agent_zero_lite.cli:main',  # Short alias
        ],
    },
    project_urls={
        "Bug Reports": "https://github.com/frdel/agent-zero-lite/issues",
        "Source": "https://github.com/frdel/agent-zero-lite",
        "Documentation": "https://github.com/frdel/agent-zero-lite#readme",
    },
    keywords="ai agent llm python automation web-ui litellm openai anthropic",
    zip_safe=False,
)
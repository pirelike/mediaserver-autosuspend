from setuptools import setup, find_packages
import os
from pathlib import Path

# Read version from version.py
with open("mediaserver_autosuspend/version.py", "r", encoding="utf-8") as f:
    exec(f.read())

# Read long description from README
with open("README.md", "r", encoding="utf-8") as f:
    long_description = f.read()

# Read requirements
with open("requirements.txt", "r", encoding="utf-8") as f:
    requirements = [line.strip() for line in f if line.strip() and not line.startswith("#")]

def get_package_data():
    """Get all non-Python files that should be included in the package."""
    package_data = {
        "mediaserver_autosuspend": [
            "config.example.json",
            "systemd/*",
            "scripts/*"
        ]
    }
    return package_data

def get_data_files():
    """Get files that should be installed to system locations."""
    return [
        # Config directory
        ("/etc/mediaserver-autosuspend", ["config.example.json"]),
        # Systemd service
        ("/etc/systemd/system", ["systemd/mediaserver-autosuspend.service"]),
        # Scripts
        ("/usr/local/bin", [
            "scripts/install.sh",
            "scripts/set-wakeup.sh"
        ])
    ]

setup(
    name="mediaserver-autosuspend",
    version=__version__,  # Version imported from version.py
    author="Pirelike",
    author_email="author@example.com",  # Replace with actual email
    description="Automatic suspension tool for media servers",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/pirelike/mediaserver-autosuspend",
    packages=find_packages(exclude=["tests*"]),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: System :: Systems Administration",
        "Topic :: System :: Power (UPS)",
        "Topic :: Multimedia :: Video",
        "Topic :: Utilities",
    ],
    python_requires=">=3.7",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "mediaserver-autosuspend=mediaserver_autosuspend.main:main",
        ],
    },
    package_data=get_package_data(),
    data_files=get_data_files(),
    include_package_data=True,
    zip_safe=False,
    test_suite="tests",
    project_urls={
        "Bug Tracker": "https://github.com/pirelike/mediaserver-autosuspend/issues",
        "Documentation": "https://github.com/pirelike/mediaserver-autosuspend/wiki",
        "Source Code": "https://github.com/pirelike/mediaserver-autosuspend",
    },
)

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

setup(
    name="mediaserver-autosuspend",
    version="1.0.0",
    author="Pirelike",
    description="Automatic suspension tool for media servers",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/pirelike/mediaserver-autosuspend",
    packages=find_packages(exclude=("tests",)),
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
    ],
    python_requires=">=3.7",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "mediaserver-autosuspend=mediaserver_autosuspend.main:main",
        ],
    },
    scripts=["scripts/install.sh", "scripts/set-wakeup.sh"],
    include_package_data=True,
)

"""Setup script for FetLife Video Scraper."""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="fetscraper",
    version="0.1.0",
    author="OEngineer",
    description="Download videos from FetLife with search and filtering",
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.8",
    install_requires=[
        "requests>=2.31.0",
        "beautifulsoup4>=4.12.0",
        "lxml>=4.9.0",
        "click>=8.1.0",
        "python-dotenv>=1.0.0",
        "tqdm>=4.66.0",
        "colorama>=0.4.6",
    ],
    entry_points={
        "console_scripts": [
            "fetscraper=src.cli:main",
        ],
    },
)

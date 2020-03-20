#!/usr/bin/env python3

"""
Automatic backups for libvirt
See:
    https://github.com/Anthony25/virt-backup
"""

from os import path
from setuptools import find_packages, setup

here = path.abspath(path.dirname(__file__))

setup(
    name="virt-backup",
    version="0.4.1",

    description="Automatic backups for libvirt",

    url="https://github.com/Anthony25/virt-backup",
    author="Anthony25 <Anthony Ruhier>",
    author_email="anthony.ruhier@gmail.com",

    license="Simplified BSD",

    classifiers=[
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3 :: Only",
        "License :: OSI Approved :: BSD License",
    ],

    keywords="libvirt",
    packages=find_packages(exclude=["example", "tests"]),
    install_requires=[
        "appdirs", "argparse", "arrow", "defusedxml", "libvirt-python", "lxml",
        "packaging", "PyYAML"
    ],
    setup_requires=['pytest-runner', ],
    tests_require=['pytest', 'pytest-cov', "pytest-mock", "deepdiff"],
    extras_require={"zstd": ["zstandard"], },
    entry_points={
        'console_scripts': [
            'virt-backup = virt_backup.__main__:cli_run',
        ],
    }
)

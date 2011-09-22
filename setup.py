#!/usr/bin/python

import os
import sys
from setuptools import setup, find_packages


def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()


requirements = []


setup(
    name = "pyucsm",
    version = "0.1.3a2",
    description = "Client library for Cisco UCS XML API",
    long_description = read('README'),
    url = 'https://github.com/chemikadze/pyucsm',
    license = 'Apache',
    author = 'Nikolay Sokolov',
    author_email = 'nsokolov@griddynamics.com',
    py_modules = ['pyucsm', 'ucsmquery'],
    classifiers = [
        'Development Status :: 3 - Alpha',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'Intended Audience :: Information Technology',
        'License :: OSI Approved :: Apache Software License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
    ],
    install_requires = requirements,

    tests_require = ["unittest"],
    test_suite = "",

    entry_points = {
        'console_scripts': ['ucsmquery = ucsmquery:main']
    }
)

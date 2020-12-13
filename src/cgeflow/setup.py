from setuptools import find_packages, setup

NAME = 'cgeflow'
VERSION = '1.0.0'
DESCRIPTION = 'Very simple workflow and job control'
URL = 'https://github.com/zwets/kcri-cge-bap'
EMAIL = 'zwets@kcri.ac.tz'
AUTHOR = 'Marco van Zwetselaar'
REQUIRES_PYTHON = '>=3.8.0'
REQUIRED = [ 'psutil' ]
EXTRAS = { }

about = {'__version__': VERSION}

setup(
    name = NAME,
    version = VERSION,
    description = DESCRIPTION,
    long_description = DESCRIPTION,
    author = AUTHOR,
    author_email = EMAIL,
    python_requires = REQUIRES_PYTHON,
    url = URL,
    packages = find_packages(exclude=['tests']),
    install_requires = REQUIRED,
    extras_require = EXTRAS,
    include_package_data = True,
    license = 'Apache License, Version 2.0',
    classifiers = ['License :: OSI Approved :: Apache Software License'],
    zip_safe = False
    )

from zkfarmer import VERSION
from setuptools import setup, find_packages
import re


def parse_requirements(file_name):
    requirements = []
    for line in open(file_name, 'r').read().split('\n'):
        if re.match(r'(\s*#)|(\s*$)', line):
            continue
        if re.match(r'\s*-e\s+', line):
            # TODO support version numbers
            requirements.append(re.sub(r'\s*-e\s+.*#egg=(.*)$', r'\1', line))
        elif re.match(r'\s*-f\s+', line):
            pass
        else:
            requirements.append(line)
    return requirements

setup(
    name='zkfarmer',
    version=VERSION,
    author='Olivier Poitrey',
    author_email='rs@dailymotion.com',
    packages=find_packages(),
    scripts=['bin/zkfarmer'],
    url='http://github.com/rs/zkfarmer',
    license='LICENSE',
    description='Easy distributed server farm management using Apache ZooKeeper.',
    long_description=open('README.md').read(),
    install_requires=parse_requirements('requirements.txt'),
    tests_require = [ "nose", "mock" ] + parse_requirements('requirements.txt'),
    test_suite="nose.collector"
)

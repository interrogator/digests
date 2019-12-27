import os

from setuptools import setup


def read(fname):
    """
    Helper to read README
    """
    return open(os.path.join(os.path.dirname(__file__), fname)).read().strip()


setup(
    name="digests",
    version="0.0.3",  # bump2version will edit this automatically!
    description="Tools for news corpora",
    long_description=read("README.md"),
    long_description_content_type="text/markdown",
    url="http://github.com/interrogator/digests",
    author="Danny McDonald",
    include_package_data=True,
    zip_safe=False,
    packages=["digests"],
    scripts=[],
    author_email="mcddjx@gmail.com",
    license="MIT",
    keywords=[],
    install_requires=["buzz"],
    dependency_links=[],
)

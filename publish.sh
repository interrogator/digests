#!/usr/bin/env bash

# fail on any error
set -e
echo "Doing $1 update"


# check formatting
flake8 digests/* tests/* setup.py
black digests/* tests/* setup.py --check
isort -m 3 -tc -c digests/* tests/* setup.py

# run tests
python -m unittest

# remove old releases
rm -r -f build dist

# bump the version
bump2version $1

# make new releases
python setup.py bdist_egg sdist

# upload
twine upload dist/*

# push to git
git push origin master --follow-tags

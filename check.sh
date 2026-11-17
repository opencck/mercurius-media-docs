#!/bin/sh
# The checks of this repository, as composer check in the PHP ones: tests and the linter.
set -e
python3 -m unittest discover -s tests -t .
python3 -m ruff check media_docs tests

PYTHON ?= python

.PHONY: test check benchmark
test:
	$(PYTHON) -m unittest discover -v

check:
	$(PYTHON) -m mypy
	$(PYTHON) -m coverage run -m unittest discover -v
	$(PYTHON) -m coverage report

benchmark:
	$(PYTHON) -m tests.properties.benchmark

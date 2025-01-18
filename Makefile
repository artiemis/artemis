ENV=.venv
BIN=$(ENV)/bin
PYTHON=$(BIN)/python
PIP=$(BIN)/pip

.PHONY: venv install dev watch clean

venv:
	python3 -m venv .venv

install:
	$(PIP) install -Ur requirements.txt

dev:
	$(PYTHON) -m artemis.bot

watch:
	pnpx nodemon -e py,toml -x $(PYTHON) -m artemis.bot

clean:
	rm -rf .venv

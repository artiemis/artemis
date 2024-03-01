ENV=env
BIN=$(ENV)/bin

install:
	$(BIN)/pip install -Ur requirements.txt

dev:
	source $(BIN)/activate; pnpx nodemon bot.py

clean:
	rm -rf venv

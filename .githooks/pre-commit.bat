flake8 . --count --max-complexity=10 --max-line-length=180 --statistics --extend-exclude build/
pycodestyle . --max-line-length=180 --exclude=build/

# lib-python-baseutils
Low level library for common functions needed by different scripts and libraries

# Dev notes
* This should run on Windows and Linux in both Python 2.7 and Python 3
* .vscode/launch.json contains a launch configuration to run the tests from VSCode
  * if windows & Python 2.7, the following is required
      * pip intall mock
* to enable git commit hooks, run the following:
    * git config core.hooksPath .githooks
    * pip install pep8
    * pip install flake8
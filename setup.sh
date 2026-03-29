#!/bin/bash
# setup.sh
pip install --upgrade pip
pip install -r requirements.txt
python -c "import main; main.init_db()"

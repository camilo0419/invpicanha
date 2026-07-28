@echo off
py -m venv .venv
call .venv\Scriptsctivate
python -m pip install --upgrade pip
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
pause

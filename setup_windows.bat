@echo off
py -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_initial_data
python manage.py cargar_catalogo_picanha
python manage.py runserver
pause

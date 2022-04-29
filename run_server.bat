cd /d %~dp0
py -3 -m venv venv
call %cd%\venv\Scripts\activate.bat
pip install Flask
set FLASK_ENV=development
flask run
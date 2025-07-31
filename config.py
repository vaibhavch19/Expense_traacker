import os

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "5b01b64773fd6fa339f9284f94e2b44757a2fbd846607ecbe2a732aaf9aa7ca2")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        "postgresql://tanu:tanu%40123@localhost/expense_db"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = 'uploads'
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'pdf'}

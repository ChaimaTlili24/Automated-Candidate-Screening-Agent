from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    fullname = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False, index=True)
    password = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="candidat")
    # roles: "candidat" | "rh"

    # ✅ Set password hashed
    def set_password(self, pwd):
        self.password = generate_password_hash(pwd)

    # ✅ Check password
    def check_password(self, pwd):
        return check_password_hash(self.password, pwd)

    def __repr__(self):
        return f"<User {self.email} - {self.role}>"

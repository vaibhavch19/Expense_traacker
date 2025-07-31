from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, FloatField, SelectField, DateField
from wtforms.validators import DataRequired, Length, EqualTo
from flask_wtf.file import FileField, FileAllowed

class RegisterForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired(), Length(min=3, max=50)])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=5)])
    confirm = PasswordField("Repeat Password", validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField("Register")

class LoginForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired()])
    password = PasswordField("Password", validators=[DataRequired()])
    submit = SubmitField("Login")

from flask_wtf.file import FileField, FileAllowed

class ExpenseForm(FlaskForm):
    description = StringField("Description", validators=[DataRequired()])
    amount = FloatField("Amount", validators=[DataRequired()])
    date = DateField("Date", validators=[DataRequired()])
    category = SelectField("Category", coerce=int)
    receipt = FileField('Upload Receipt',
                        validators=[FileAllowed(['jpg', 'jpeg', 'png', 'gif', 'bmp', 'pdf'], 'Images only!')])
    submit = SubmitField("Add Expense")

class BudgetForm(FlaskForm):
    category = SelectField("Category", coerce=int)
    month = StringField("Month (YYYY-MM)", validators=[DataRequired(), Length(min=7, max=7)])
    amount = FloatField("Budget Amount", validators=[DataRequired()])
    submit = SubmitField("Set Budget")

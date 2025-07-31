import os
import secrets
from flask import Flask, render_template, redirect, url_for, flash, request, send_file, abort, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, current_user, login_required
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from config import Config
from models import db, User, Category, Expense, Budget
from forms import RegisterForm, LoginForm, ExpenseForm, BudgetForm

app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Ensure the upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))  # SQLAlchemy 2.0 style

def create_tables():
    with app.app_context():
        db.create_all()

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config.get('ALLOWED_EXTENSIONS', {'png', 'jpg', 'jpeg', 'gif', 'bmp'})

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('landing.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        if User.query.filter_by(username=form.username.data).first():
            flash("Username already exists. Please choose a different one.", "error")
            return redirect(url_for('register'))
        new_user = User(username=form.username.data, password=generate_password_hash(form.password.data))
        db.session.add(new_user)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("Username already exists or database error.", "error")
            return redirect(url_for('register'))
        except SQLAlchemyError:
            db.session.rollback()
            flash("Database error occurred. Please try later.", "error")
            return redirect(url_for('register'))

        default_categories = ['Food', 'Transport', 'Bills', 'Health', 'Other']
        try:
            for cat_name in default_categories:
                category = Category(name=cat_name, user_id=new_user.id)
                db.session.add(category)
            db.session.commit()
        except Exception:
            db.session.rollback()
        flash("Registration successful. Please log in.", "success")
        return redirect(url_for('login'))
    elif form.is_submitted():
        flash("Please correct errors in the form.", "error")
    return render_template('register.html', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and check_password_hash(user.password, form.password.data):
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password', 'error')
    elif form.is_submitted():
        flash('Please fill all fields correctly.', 'error')
    return render_template('login.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/dashboard', methods=['GET', 'POST'])
@login_required
def dashboard():
    category_filter = request.args.get('category')
    month = request.args.get('month')
    query = Expense.query.filter_by(user_id=current_user.id)
    if category_filter and category_filter != 'all':
        query = query.join(Category).filter(Category.id == int(category_filter))
    if month:
        try:
            year, mon = map(int, month.split('-'))
            query = query.filter(db.extract('year', Expense.date) == year,
                                 db.extract('month', Expense.date) == mon)
        except Exception:
            pass
    expenses = query.order_by(Expense.date.desc()).all()
    categories = Category.query.filter_by(user_id=current_user.id).all()

    budget_feedback = {}
    current_month = datetime.now().strftime("%Y-%m")

    for cat in categories:
        budget = Budget.query.filter_by(user_id=current_user.id, category_id=cat.id, month=current_month).first()
        total_spent = db.session.query(db.func.sum(Expense.amount))\
                        .filter_by(user_id=current_user.id, category_id=cat.id)\
                        .filter(db.extract('year', Expense.date) == int(current_month[:4]),
                                db.extract('month', Expense.date) == int(current_month[5:7])
                        ).scalar() or 0
        if budget:
            diff = total_spent - budget.amount
            if diff > 0:
                msg = f"Over budget in {cat.name} by ₹{diff:.2f}. Consider reducing expenses."
                status = 'warn'
            elif diff == 0:
                msg = f"At exact budget for {cat.name}. Well done!"
                status = 'info'
            else:
                msg = f"Under budget in {cat.name} by ₹{abs(diff):.2f}. Keep saving!"
                status = 'success'
            budget_feedback[cat.name] = {'msg': msg, 'status': status}

    return render_template('dashboard.html', expenses=expenses, categories=categories, budget_feedback=budget_feedback,
                           current_month=current_month)

def get_budget_status(user_id, category_id, month):
    budget = Budget.query.filter_by(user_id=user_id, category_id=category_id, month=month).first()
    category_expenses = db.session.query(db.func.sum(Expense.amount))\
        .filter_by(user_id=user_id, category_id=category_id)\
        .filter(db.extract('year', Expense.date) == int(month.split('-')[0]),
                db.extract('month', Expense.date) == int(month.split('-')[1]))\
        .scalar() or 0
    if not budget:
        return None, category_expenses
    diff = category_expenses - budget.amount
    return diff, budget.amount

@app.route('/add', methods=['GET', 'POST'])
@login_required
def add_expense():
    form = ExpenseForm()
    form.category.choices = [(c.id, c.name) for c in Category.query.filter_by(user_id=current_user.id).all()]
    if form.validate_on_submit():
        receipt_filename = None
        if form.receipt and form.receipt.data:
            file = form.receipt.data
            if allowed_file(file.filename):
                random_hex = secrets.token_hex(8)
                filename = secure_filename(file.filename)
                file_ext = filename.rsplit('.', 1)[1].lower()
                new_filename = f"{current_user.id}_{random_hex}.{file_ext}"
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], new_filename)
                file.save(file_path)
                receipt_filename = new_filename
            else:
                flash("Invalid image format. Upload jpg, jpeg, png, gif, bmp.", "error")
                return redirect(url_for('add_expense'))

        expense = Expense(
            description=form.description.data,
            amount=form.amount.data,
            date=form.date.data,
            category_id=form.category.data,
            user_id=current_user.id,
            receipt_path=receipt_filename if receipt_filename else None
        )
        db.session.add(expense)
        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            flash("Failed to add expense. Please try again.", "error")
            return redirect(url_for('add_expense'))

        this_month = expense.date.strftime("%Y-%m")
        diff, budget_amt = get_budget_status(current_user.id, expense.category_id, this_month)
        category = db.session.get(Category, expense.category_id)

        if diff is not None and budget_amt is not None:
            if diff > 0:
                flash(f"⚠️ Budget exceeded for {category.name} by ₹{diff:.2f}. Try saving!", "warn")
            elif diff == 0:
                flash(f"On budget for {category.name}. Well controlled!", "info")
            else:
                flash(f"🎉 You saved ₹{abs(diff):.2f} under budget in {category.name}. Great job!", "success")
        else:
            flash("Expense added! (No budget set for this category/month.)", "info")
        return redirect(url_for('dashboard'))
    elif form.is_submitted():
        flash("Please correct the errors in the form.", "error")
    return render_template('add_expense.html', form=form)

@app.route("/set_budget", methods=['GET', 'POST'])
@login_required
def set_budget():
    form = BudgetForm()
    form.category.choices = [(c.id, c.name) for c in Category.query.filter_by(user_id=current_user.id).all()]
    if form.validate_on_submit():
        month = form.month.data
        budget = Budget.query.filter_by(user_id=current_user.id, category_id=form.category.data, month=month).first()
        if budget:
            budget.amount = form.amount.data
            message = "Budget updated!"
        else:
            budget = Budget(user_id=current_user.id, category_id=form.category.data, month=month, amount=form.amount.data)
            db.session.add(budget)
            message = "Budget set!"
        try:
            db.session.commit()
            flash(message, "success")
        except Exception:
            db.session.rollback()
            flash("Error saving budget. Please try again.", "error")
        return redirect(url_for('set_budget'))
    budgets = Budget.query.filter_by(user_id=current_user.id).all()
    budgets_enriched = [{
        "id": b.id,
        "month": b.month,
        "category": db.session.get(Category, b.category_id).name,
        "amount": b.amount
    } for b in budgets]
    return render_template("set_budget.html", form=form, budgets=budgets_enriched)

@app.route('/export')
@login_required
def export_csv():
    expenses = Expense.query.filter_by(user_id=current_user.id).all()
    data = [{
        "Description": e.description,
        "Amount": e.amount,
        "Category": e.category.name if e.category else "",
        "Date": e.date.strftime('%Y-%m-%d')
    } for e in expenses]
    import pandas as pd
    from io import BytesIO
    df = pd.DataFrame(data)
    buf = BytesIO()
    df.to_csv(buf, index=False)
    buf.seek(0)
    return send_file(buf, mimetype='text/csv', download_name='expenses.csv', as_attachment=True)

@app.route('/uploads/<filename>')
@login_required
def receipt_image(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route("/edit_budget/<int:budget_id>", methods=["GET", "POST"])
@login_required
def edit_budget(budget_id):
    budget = Budget.query.filter_by(id=budget_id, user_id=current_user.id).first_or_404()
    form = BudgetForm(obj=budget)
    form.category.choices = [(c.id, c.name) for c in Category.query.filter_by(user_id=current_user.id).all()]

    if form.validate_on_submit():
        budget.category_id = form.category.data
        budget.month = form.month.data
        budget.amount = form.amount.data
        try:
            db.session.commit()
            flash("Budget updated successfully.", "success")
            return redirect(url_for("set_budget"))
        except Exception:
            db.session.rollback()
            flash("Error updating budget. Please try again.", "error")
            return redirect(url_for("edit_budget", budget_id=budget_id))
    else:
        if request.method == "GET":
            form.category.data = budget.category_id

    return render_template("edit_budget.html", form=form)

@app.route('/delete_budget/<int:budget_id>', methods=['POST'])
@login_required
def delete_budget(budget_id):
    budget = Budget.query.filter_by(id=budget_id, user_id=current_user.id).first_or_404()
    try:
        db.session.delete(budget)
        db.session.commit()
        flash('Budget deleted successfully.', 'success')
    except Exception:
        db.session.rollback()
        flash('Error deleting budget.', 'error')
    return redirect(url_for('set_budget'))

@app.route("/edit_expense/<int:expense_id>", methods=["GET", "POST"])
@login_required
def edit_expense(expense_id):
    expense = Expense.query.filter_by(id=expense_id, user_id=current_user.id).first_or_404()
    form = ExpenseForm(obj=expense)
    form.category.choices = [(c.id, c.name) for c in Category.query.filter_by(user_id=current_user.id).all()]

    if form.validate_on_submit():
        expense.description = form.description.data
        expense.amount = form.amount.data
        expense.date = form.date.data
        expense.category_id = form.category.data

        # Handle receipt update if a new file is uploaded
        if form.receipt.data:
            file = form.receipt.data
            # Delete the old receipt file if exists
            if expense.receipt_path:
                try:
                    old_path = os.path.join(app.config['UPLOAD_FOLDER'], expense.receipt_path)
                    if os.path.exists(old_path):
                        os.remove(old_path)
                except Exception:
                    # Log error or ignore
                    pass

            if allowed_file(file.filename):
                random_hex = secrets.token_hex(8)
                filename = secure_filename(file.filename)
                file_ext = filename.rsplit('.', 1)[1].lower()
                new_filename = f"{current_user.id}_{random_hex}.{file_ext}"
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], new_filename)
                file.save(file_path)
                expense.receipt_path = new_filename
            else:
                flash("Invalid image format for receipt. Upload jpg, jpeg, png, gif, bmp.", "error")
                return redirect(url_for('edit_expense', expense_id=expense_id))

        try:
            db.session.commit()
            flash("Expense updated successfully.", "success")
            return redirect(url_for("dashboard"))
        except Exception:
            db.session.rollback()
            flash("Error updating expense. Please try again.", "error")
            return redirect(url_for("edit_expense", expense_id=expense_id))
    else:
        if request.method == "GET":
            form.category.data = expense.category_id

    return render_template("edit_expense.html", form=form, expense=expense)

@app.route('/delete_expense/<int:expense_id>', methods=['POST'])
@login_required
def delete_expense(expense_id):
    expense = Expense.query.filter_by(id=expense_id, user_id=current_user.id).first_or_404()
    try:
        db.session.delete(expense)
        db.session.commit()
        flash('Expense deleted successfully.', 'success')
    except Exception:
        db.session.rollback()
        flash('Error deleting expense.', 'error')
    return redirect(url_for('dashboard'))

if __name__ == "__main__":
    create_tables()
    app.run(debug=True)

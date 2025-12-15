from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required
from extensions import db
from models import User

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        from flask import current_app
        current_app.logger.info(f"Login attempt for: {username}")
        
        if user:
            current_app.logger.info(f"User found: {user.username}. Checking password...")
            if user.check_password(password):
                current_app.logger.info("Password Correct. Logging in...")
                login_user(user)
                return redirect(url_for('orders.dashboard'))
            else:
                current_app.logger.warning("Password verification FAILED.")
        else:
            current_app.logger.warning("User NOT FOUND.")

        flash('Invalid username or password')
            
    return render_template('login.html')

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))

@auth_bp.route('/register', methods=['POST'])
def register():
    # Helper endpoint to create users (secured or public for now as per req)
    data = request.json
    username = data.get('username')
    password = data.get('password')
    company = data.get('company')
    phone = data.get('phone') # Postgres user phone column
    
    if User.query.filter_by(username=username).first():
        return {'error': 'User already exists'}, 400
        
    from flask import current_app
    user = User(
        username=username,
        company=company,
        phone_number=phone,
        system_prompt=current_app.config['DEFAULT_SYSTEM_PROMPT'],
        menu=""
    )
    user.set_password(password)
    
    db.session.add(user)
    db.session.commit()
    
    return {'message': 'User created successfully'}, 201

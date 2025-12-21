from flask import Blueprint, request, jsonify, current_app
from flask_login import login_user, logout_user, login_required, current_user
from extensions import db
from models.models import User, Company
from utils.phone import normalize_phone

auth_bp = Blueprint('auth', __name__, url_prefix='/api')

@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    current_app.logger.info(f"Login attempt for: {username}")
    
    user = User.query.filter_by(username=username).first()
    
    if user and user.check_password(password):
        login_user(user)
        current_app.logger.info(f"✅ User {username} logged in successfully")
        return jsonify({
            'success': True,
            'user': user.to_dict()
        })
    
    current_app.logger.warning(f"❌ Login failed for: {username}")
    return jsonify({'success': False, 'error': 'Identifiants invalides'}), 401

@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    return jsonify({'success': True})

@auth_bp.route('/me')
def me():
    if current_user.is_authenticated:
        return jsonify({
            'authenticated': True,
            'user': current_user.to_dict()
        })
    return jsonify({'authenticated': False}), 200

@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    company = data.get('company')
    phone = data.get('phone')
    
    if User.query.filter_by(username=username).first():
        return jsonify({'error': 'Cet utilisateur existe déjà'}), 400
        
    # Create Company first
    new_company = Company(
        name=company or f"{username}'s Kitchen",
        phone_number=normalize_phone(phone),
        system_prompt=current_app.config.get('DEFAULT_SYSTEM_PROMPT', "You are a helpful assistant."),
        menu="",
        voice="Charon"  # Default voice for new agents
    )
    db.session.add(new_company)
    db.session.flush()

    user = User(
        username=username,
        company_id=new_company.id,
        is_admin=True # First user is admin of their company
    )
    user.set_password(password)
    
    db.session.add(user)
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Compte créé avec succès', 'user': user.to_dict()}), 201

@auth_bp.route('/profile', methods=['POST'])
@login_required
def update_profile():
    data = request.json
    
    # Non-superadmins only modify their own company settings if they are is_admin
    if current_user.is_superadmin:
        # Superadmin can update everything if they are linked to a company, 
        # but usually they manage via /admin routes.
        # However, let's allow them to update their own profile/company here too.
        pass

    if current_user.is_admin or current_user.is_superadmin:
        company = current_user.company_ref
        if company:
            if 'agent_on' in data:
                company.agent_on = data.get('agent_on')
            if 'voice' in data:
                company.voice = data.get('voice')
            
            # Superadmin only fields
            if current_user.is_superadmin:
                if 'system_prompt' in data:
                    company.system_prompt = data.get('system_prompt')
                if 'phone_number' in data:
                    company.phone_number = normalize_phone(data.get('phone_number'))
                if 'menu' in data:
                    company.menu = data.get('menu')
    
    db.session.commit()
    return jsonify({
        'success': True,
        'user': current_user.to_dict()
    })

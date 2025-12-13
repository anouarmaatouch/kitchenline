from flask import Blueprint, render_template, request, jsonify, current_app, redirect, url_for, flash
from flask_login import login_required, current_user
from extensions import db
from models import User
from werkzeug.security import generate_password_hash
import base64
import requests
import json

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

@admin_bp.before_request
@login_required
def admin_required():
    if not current_user.is_admin:
        flash("Access Denied: Admin only.")
        return redirect(url_for('orders.dashboard'))

@admin_bp.route('/')
def index():
    users = User.query.all()
    return render_template('admin.html', users=users)

@admin_bp.route('/users', methods=['POST'])
def manage_user():
    action = request.form.get('action')
    
    if action == 'create':
        username = request.form.get('username')
        password = request.form.get('password')
        phone = request.form.get('phone')
        company = request.form.get('company')
        if User.query.filter_by(username=username).first():
            flash('Username already exists.')
        else:
            user = User(username=username, phone_number=phone, company=company)
            user.set_password(password)
            user.is_admin = 'is_admin' in request.form
            db.session.add(user)
            db.session.commit()
            flash('User created.')
            
    elif action == 'edit':
        user_id = request.form.get('user_id')
        user = User.query.get(user_id)
        if user:
            user.voice = request.form.get('voice')
            user.agent_on = 'agent_on' in request.form
            user.system_prompt = request.form.get('system_prompt')
            db.session.commit()
            flash('User updated.')

    elif action == 'delete':
        user_id = request.form.get('user_id')
        user = User.query.get(user_id)
        if user:
            db.session.delete(user)
            db.session.commit()
            flash('User deleted.')
            
    return redirect(url_for('admin.index'))

@admin_bp.route('/menu/upload', methods=['POST'])
def upload_menu():
    user_id = request.form.get('user_id')
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    image_file = request.files.get('menu_image')
    if not image_file:
         return jsonify({'error': 'No image provided'}), 400
         
    # OpenAI Vision Logic
    try:
        image_data = base64.b64encode(image_file.read()).decode('utf-8')
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {current_app.config['OPENAI_API_KEY']}"
        }
        
        payload = {
            "model": "gpt-4o",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Extract strictly only the menu items and their prices from this image. output the result as a raw text list (Item: Price). Do NOT include any introductory text, markdown formatting (like ```), headers, footers, or any conversational filler. Just the data."},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}}
                    ]
                }
            ],
            "max_tokens": 1000
        }
        
        response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
        response_data = response.json()
        menu_text = response_data['choices'][0]['message']['content']
        
        user.menu = menu_text
        db.session.commit()
        
        return jsonify({'success': True, 'menu_text': menu_text})
        
    except Exception as e:
        current_app.logger.error(f"Vision API Error: {e}")
        return jsonify({'error': str(e)}), 500

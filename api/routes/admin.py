from flask import Blueprint, request, jsonify, current_app, send_file
from flask_login import login_required, current_user
from extensions import db
from models.models import User, MenuImage
from config.constants import DEFAULT_SYSTEM_PROMPTS
from utils.phone import normalize_phone
import os
import io
import time

admin_bp = Blueprint('admin_api', __name__, url_prefix='/api/admin')

@admin_bp.before_request
@login_required
def admin_required():
    if not current_user.is_superadmin:
        return jsonify({'error': 'Accès refusé: Superadmin uniquement'}), 403

@admin_bp.route('/users', methods=['GET'])
def get_users():
    users = User.query.all()
    return jsonify([u.to_dict() for u in users])

@admin_bp.route('/users', methods=['POST'])
def manage_user():
    data = request.json
    action = data.get('action')
    
    if action == 'create':
        username = data.get('username')
        password = data.get('password')
        phone = data.get('phone')
        company = data.get('company')
        language = data.get('language', 'ar-ma')
        
        if User.query.filter_by(username=username).first():
            return jsonify({'error': 'Cet utilisateur existe déjà'}), 400
            
        default_prompt = DEFAULT_SYSTEM_PROMPTS.get(language, DEFAULT_SYSTEM_PROMPTS['ar-ma'])
        
        # Superadmin can specify company_id
        company_id = data.get('company_id')
        
        # If no company_id provided but company_name is, create new Company
        if not company_id and company:
            from models.models import Company
            new_company = Company(
                name=company,
                phone_number=normalize_phone(phone) if phone else None,
                voice='Charon',
                agent_on=True,
                system_prompt=DEFAULT_SYSTEM_PROMPTS.get(language, DEFAULT_SYSTEM_PROMPTS['ar-ma'])
            )
            db.session.add(new_company)
            db.session.flush()
            company_id = new_company.id

        user = User(
            username=username, 
            company_id=company_id,
            is_admin=data.get('is_admin', False),
            is_superadmin=data.get('is_superadmin', False)
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        return jsonify({'success': True, 'user': user.to_dict()}), 201
            
    elif action == 'edit':
        user_id = data.get('user_id')
        user = User.query.get(user_id)
        if user:
            if user.company_ref:
                if 'company' in data:
                    user.company_ref.name = data.get('company')
                if 'phone_number' in data: # Support phone number update
                    user.company_ref.phone_number = normalize_phone(data.get('phone_number'))
                if 'voice' in data:
                    user.company_ref.voice = data.get('voice')

                if 'agent_on' in data:
                    user.company_ref.agent_on = data.get('agent_on')
                if 'system_prompt' in data:
                    user.company_ref.system_prompt = data.get('system_prompt')
                if 'menu' in data:
                    user.company_ref.menu = data.get('menu')

            # Allow superadmin to update user permissions
            if current_user.is_superadmin:
                if 'is_admin' in data:
                    user.is_admin = data.get('is_admin')

            db.session.commit()
            return jsonify({'success': True, 'user': user.to_dict()})

    elif action == 'delete':
        user_id = data.get('user_id')
        user = User.query.get(user_id)
        if user:
            db.session.delete(user)
            db.session.commit()
            return jsonify({'success': True})
            
    return jsonify({'error': 'Action non valide'}), 400

@admin_bp.route('/menu/save', methods=['POST'])
def save_menu_images():
    user_id = request.form.get('user_id')
    user = User.query.get(user_id)
    if not user or not user.company_ref:
        return jsonify({'error': 'Utilisateur ou entreprise non trouvé'}), 404

    files = request.files.getlist('menu_images')
    if not files:
         return jsonify({'error': 'Aucune image fournie'}), 400
         
    try:
        for f in files:
            image_bytes = f.read()
            if not image_bytes:
                continue
            menu_img = MenuImage(company_id=user.company_ref.id, image_data=image_bytes, filename=f.filename)
            db.session.add(menu_img)
        
        db.session.commit()
        return jsonify({
            'success': True, 
            'menu_images': [img.id for img in user.company_ref.menu_images]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/menu/extract', methods=['POST'])
def extract_menu():
    user_id = request.form.get('user_id')
    user = User.query.get(user_id)
    if not user or not user.company_ref:
        return jsonify({'error': 'Utilisateur ou entreprise non trouvé'}), 404

    files = request.files.getlist('menu_images')
    
    try:
        from google import genai
        from google.genai import types
        
        creds_path = os.path.abspath("vertex-json.json")
        if os.path.exists(creds_path):
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds_path
        
        client = genai.Client(
            vertexai=True,
            project="polar-equinox-472800-j2",
            location="us-central1"
        )
        
        prompt_parts = [
            "Extract strictly only the menu items and their prices from these images. Output the result as a raw text list (Item: Price). Do NOT include any introductory text, markdown formatting, headers, footers, or any conversational filler. Just the data."
        ]
        
        if files:
            for f in files:
                image_bytes = f.read()
                if not image_bytes:
                    continue
                prompt_parts.append(
                    types.Part(inline_data=types.Blob(data=image_bytes, mime_type="image/jpeg"))
                )
        else:
            company = user.company_ref
            if not company or not company.menu_images:
                return jsonify({'error': 'Aucune image à extraire'}), 400
            for img in company.menu_images:
                prompt_parts.append(
                    types.Part(inline_data=types.Blob(data=img.image_data, mime_type="image/jpeg"))
                )

        start_time = time.time()
        current_app.logger.info(f"Starting Gemini extraction for company {user.company_ref.id}")
        
        response = client.models.generate_content(
            model="gemini-2.0-flash-exp",
            contents=prompt_parts
        )
        
        duration = time.time() - start_time
        current_app.logger.info(f"Gemini extraction completed in {duration:.2f}s")
        
        menu_text = response.text
        user.company_ref.menu = menu_text
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'menu_text': menu_text
        })
        
    except Exception as e:
        import traceback
        error_msg = traceback.format_exc()
        current_app.logger.error(f"Vertex AI Vision Error for user {user_id}:\n{error_msg}")
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/menu/image/<int:image_id>')
def get_menu_image(image_id):
    image = MenuImage.query.get_or_404(image_id)
    return send_file(
        io.BytesIO(image.image_data),
        mimetype='image/jpeg',
        as_attachment=False,
        download_name=image.filename or f"menu_{image_id}.jpg"
    )

@admin_bp.route('/menu/image/<int:image_id>', methods=['DELETE'])
def delete_menu_image(image_id):
    image = MenuImage.query.get_or_404(image_id)
    # Superadmin can delete any image
    db.session.delete(image)
    db.session.commit()
    return jsonify({'success': True})

@admin_bp.route('/menu/images', methods=['GET'])
def get_menu_images():
    target_user_id = request.args.get('user_id')
    
    if target_user_id:
        user = User.query.get(target_user_id)
        if not user or not user.company_ref:
            return jsonify([]) # Return empty if no company
        company_id = user.company_ref.id
    elif current_user.company_ref:
        company_id = current_user.company_ref.id
    else:
        return jsonify([])

    images = MenuImage.query.filter_by(company_id=company_id).all()
    return jsonify([{'id': img.id, 'filename': img.filename, 'created_at': img.created_at.isoformat()} for img in images])

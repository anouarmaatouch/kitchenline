import os
from flask import Flask, jsonify, send_from_directory
from config.config import Config
from extensions import db, sock
from flask_login import LoginManager
from flask_cors import CORS
from models.models import User

def create_app():
    # Configure Flask to serve the React build in production
    template_dir = os.path.abspath('../web/dist')
    static_dir = os.path.abspath('../web/dist')
    
    app = Flask(__name__, 
                static_folder=static_dir, 
                static_url_path='/static',
                template_folder=template_dir)
    
    app.config.from_object(Config)

    # Required for Fly.io / Heroku (Handles HTTPS headers from Load Balancer)
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    # Configure Logging
    import logging
    import sys
    
    if not app.debug and not app.testing:
        # Production logging
        pass

    # Ensure logs go to stdout for Docker
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)
    
    # Also configure root logger for other modules (like voice.py if using print/logging)
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(logging.INFO)

    # Initialize extensions
    CORS(app)
    db.init_app(app)
    sock.init_app(app)
    
    login_manager = LoginManager()
    login_manager.login_view = 'auth.login'
    login_manager.init_app(app)
    
    @login_manager.unauthorized_handler
    def unauthorized():
        return jsonify({'error': 'Non autorisé', 'authenticated': False}), 401

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Register Blueprints
    from routes.auth import auth_bp
    from routes.orders import orders_bp
    from routes.voice import voice_bp
    from routes.admin import admin_bp
    from routes.notifications import notifications_bp
    from routes.test_routes import test_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(orders_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(voice_bp)
    app.register_blueprint(notifications_bp)
    app.register_blueprint(test_bp)
    
    with app.app_context():
        db.create_all()
        
    @app.route('/', defaults={'path': ''})
    @app.route('/<path:path>')
    def serve(path):
        if path != "" and os.path.exists(app.static_folder + '/' + path):
            return send_from_directory(app.static_folder, path)
        
        # If path starts with /api, return 404 json instead of index.html
        if path.startswith('api/'):
            return jsonify({'error': 'Not found'}), 404
            
        return send_from_directory(app.static_folder, 'index.html')

    return app

app = create_app()

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)

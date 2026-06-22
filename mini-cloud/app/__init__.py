import os
from flask import Flask, render_template
from app.database import init_db
from app.auth.routes import auth_bp
from app.compute.routes import compute_bp
from app.images.routes import images_bp
from app.network.routes import network_bp
from app.network.sg_routes import sg_bp
from app.keypairs.routes import keypairs_bp
from app.storage.routes import storage_bp
from app.monitoring.routes import monitoring_bp


def restore_all_sg_chains():
    # Re-apply all iptables chains from DB after a system restart (iptables rules are not persistent).
    # Called once at startup before serving any requests.
    from app.network.models import get_all_vms_with_security_groups, get_all_vm_sg_rules
    from app.network.sg_manager import rebuild_vm_sg_chain

    for vm_id in get_all_vms_with_security_groups():
        inbound_rules = [r for r in get_all_vm_sg_rules(vm_id) if r['direction'] == 'inbound']
        try:
            rebuild_vm_sg_chain(vm_id, inbound_rules)
        except RuntimeError:
            pass  # VM not running — chain will be built when VM next starts


def create_app():
    # template_folder এবং static_folder root থেকে relative path দিতে হয়
    app = Flask(
        __name__,
        template_folder=os.path.join(os.path.dirname(__file__), '..', 'dashboard', 'templates'),
        static_folder=os.path.join(os.path.dirname(__file__), '..', 'dashboard', 'static'),
    )

    # App start হওয়ার সাথে সাথে DB tables তৈরি হয়ে যাবে (না থাকলে)
    init_db()

    # Restore security group iptables chains that were lost when the host rebooted
    restore_all_sg_chains()

    # Auth blueprint register — সব /api/v1/auth/* routes এখানে থাকবে
    app.register_blueprint(auth_bp)
    app.register_blueprint(compute_bp)
    app.register_blueprint(images_bp)
    app.register_blueprint(network_bp)
    app.register_blueprint(sg_bp)
    app.register_blueprint(keypairs_bp)
    app.register_blueprint(storage_bp)
    app.register_blueprint(monitoring_bp)

    # Dashboard page routes
    @app.route('/')
    def login_page():
        return render_template('login.html')

    @app.route('/register')
    def register_page():
        return render_template('register.html')

    @app.route('/dashboard')
    def dashboard_page():
        return render_template('dashboard.html')

    return app

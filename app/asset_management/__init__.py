from flask import Blueprint

asset_management_bp = Blueprint('asset_management', __name__, template_folder='templates', # Specifies where templates for this blueprint are located
    static_folder='static',    # Optional: Specifies static folder if blueprint has its own
    url_prefix='/asset-management')
from . import routes, models, schemas, services

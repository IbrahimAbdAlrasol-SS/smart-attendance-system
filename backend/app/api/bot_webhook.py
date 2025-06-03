"""Bot webhook API endpoints."""
from flask import Blueprint
from app.utils.helpers import success_response

bot_bp = Blueprint('bot', __name__)

@bot_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return success_response(message='Bot service is running')

@bot_bp.route('/webhook', methods=['POST'])
def webhook():
    """Bot webhook endpoint."""
    return success_response(message='Webhook received')
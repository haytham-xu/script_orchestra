"""
Clipboard Share Controller

REST API endpoints for clipboard sharing.
"""
from flask import request, jsonify
from flask_restx import Namespace, Resource, fields
from .service import get_service
from .websocket_service import broadcast_clipboard_update

ns = Namespace("clipboard", description="Clipboard sharing operations")

# API Models
clipboard_input_model = ns.model('ClipboardInput', {
    'content': fields.String(required=True, description='Clipboard text content'),
    'source': fields.String(default='web', description='Source of content (web, mac, windows)')
})

clipboard_item_model = ns.model('ClipboardItem', {
    'id': fields.Integer(description='Unique item ID'),
    'content': fields.String(description='Clipboard text content'),
    'source': fields.String(description='Source of content'),
    'timestamp': fields.String(description='ISO format timestamp'),
    'length': fields.Integer(description='Content length in characters')
})


@ns.route('/add')
class ClipboardAddResource(Resource):
    @ns.expect(clipboard_input_model)
    @ns.marshal_with(clipboard_item_model)
    def post(self):
        """Add new clipboard content and broadcast to all clients"""
        data = request.get_json()

        if not data or 'content' not in data:
            ns.abort(400, "Missing 'content' in request body")

        content = data['content']
        source = data.get('source', 'web')

        try:
            service = get_service()
            item = service.add_content(content, source)

            # Broadcast to all connected WebSocket clients
            broadcast_clipboard_update(item)

            print(f"[ClipboardShare] Added content (ID={item['id']}, source={source}, length={len(content)})")

            return item, 201

        except ValueError as e:
            ns.abort(400, str(e))
        except Exception as e:
            print(f"[ClipboardShare] Error adding content: {e}")
            import traceback
            traceback.print_exc()
            ns.abort(500, f"Internal error: {str(e)}")


@ns.route('/latest')
class ClipboardLatestResource(Resource):
    @ns.marshal_with(clipboard_item_model)
    def get(self):
        """Get the most recent clipboard content"""
        service = get_service()
        item = service.get_latest()

        if item is None:
            ns.abort(404, "No clipboard content available")

        return item


@ns.route('/history')
class ClipboardHistoryResource(Resource):
    @ns.marshal_list_with(clipboard_item_model)
    def get(self):
        """Get clipboard history (default: 20 items)"""
        limit = request.args.get('limit', default=20, type=int)

        if limit < 1 or limit > 100:
            ns.abort(400, "Limit must be between 1 and 100")

        service = get_service()
        history = service.get_history(limit)

        return history


@ns.route('/<int:item_id>')
class ClipboardItemResource(Resource):
    @ns.marshal_with(clipboard_item_model)
    def get(self, item_id):
        """Get specific clipboard item by ID"""
        service = get_service()
        item = service.get_by_id(item_id)

        if item is None:
            ns.abort(404, f"Clipboard item {item_id} not found")

        return item


@ns.route('/clear')
class ClipboardClearResource(Resource):
    def delete(self):
        """Clear all clipboard history"""
        service = get_service()
        count = service.clear_history()

        return {
            "message": f"Cleared {count} clipboard items",
            "count": count
        }, 200

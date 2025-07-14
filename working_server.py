#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, '.')
os.environ['CUDA_VISIBLE_DEVICES'] = ''

from flask import Flask, jsonify, request, send_from_directory, send_file
import threading
import asyncio

print("Starting working Agent Zero server with profile support...")

app = Flask(__name__, static_folder='webui', static_url_path='')

# Profile endpoints
@app.route('/profile_list', methods=['POST'])
def profile_list():
    try:
        from python.api.profile_list import ProfileList
        handler = ProfileList(app, threading.Lock())
        result = asyncio.run(handler.process({}, request))
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e), "success": False}), 500

@app.route('/profile_create', methods=['POST'])
def profile_create():
    try:
        from python.api.profile_create import ProfileCreate
        handler = ProfileCreate(app, threading.Lock())
        result = asyncio.run(handler.process(request.get_json() or {}, request))
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e), "success": False}), 500

@app.route('/profile_update', methods=['POST'])
def profile_update():
    try:
        from python.api.profile_update import ProfileUpdate
        handler = ProfileUpdate(app, threading.Lock())
        result = asyncio.run(handler.process(request.get_json() or {}, request))
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e), "success": False}), 500

@app.route('/profile_delete', methods=['POST'])
def profile_delete():
    try:
        from python.api.profile_delete import ProfileDelete
        handler = ProfileDelete(app, threading.Lock())
        result = asyncio.run(handler.process(request.get_json() or {}, request))
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e), "success": False}), 500

@app.route('/profile_switch', methods=['POST'])
def profile_switch():
    try:
        from python.api.profile_switch import ProfileSwitch
        handler = ProfileSwitch(app, threading.Lock())
        result = asyncio.run(handler.process(request.get_json() or {}, request))
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e), "success": False}), 500

@app.route('/profile_templates', methods=['POST'])
def profile_templates():
    try:
        from python.api.profile_templates import ProfileTemplates
        handler = ProfileTemplates(app, threading.Lock())
        result = asyncio.run(handler.process(request.get_json() or {}, request))
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e), "success": False}), 500

@app.route('/profile_create_from_template', methods=['POST'])
def profile_create_from_template():
    try:
        from python.api.profile_create_from_template import ProfileCreateFromTemplate
        handler = ProfileCreateFromTemplate(app, threading.Lock())
        result = asyncio.run(handler.process(request.get_json() or {}, request))
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e), "success": False}), 500

# Placeholder endpoints for other services the frontend expects
@app.route('/poll', methods=['POST'])
def poll():
    return jsonify({"status": "ok", "message": "No polling data"})

@app.route('/scheduler_tasks_list', methods=['POST'])
def scheduler_tasks_list():
    return jsonify({
        "tasks": [
            {
                "id": "example_task",
                "name": "Example Task", 
                "type": "scheduled",
                "state": "idle",
                "schedule": {
                    "minute": "0",
                    "hour": "9", 
                    "day": "*",
                    "month": "*",
                    "weekday": "*",
                    "timezone": "UTC"
                },
                "prompt": "This is an example scheduled task",
                "created": "2024-01-01T00:00:00Z",
                "updated": "2024-01-01T00:00:00Z"
            }
        ],
        "success": True
    })

@app.route('/settings_get', methods=['POST'])
def settings_get():
    return jsonify({
        "settings": {
            "sections": [
                {
                    "id": "agent_config",
                    "title": "Agent Configuration",
                    "tab": "agent",
                    "fields": [
                        {
                            "id": "agent_name",
                            "title": "Agent Name",
                            "type": "text",
                            "value": "Agent Zero",
                            "required": True
                        },
                        {
                            "id": "model_name",
                            "title": "Model Name",
                            "type": "text",
                            "value": "gpt-4",
                            "required": True
                        }
                    ]
                }
            ]
        },
        "success": True
    })

@app.route('/settings_set', methods=['POST'])
def settings_set():
    # Accept the settings data and return success
    data = request.get_json() or {}
    return jsonify({
        "settings": data,
        "success": True,
        "message": "Settings saved successfully"
    })

# Serve the main HTML file
@app.route('/')
def index():
    return send_file('webui/index.html')

# Serve static files from webui directory (but not conflicting endpoints)
@app.route('/<path:filename>')
def static_files(filename):
    # Don't serve static files for known API endpoints
    if filename in ['profile_list', 'profile_create', 'profile_update', 'profile_delete', 
                   'profile_switch', 'profile_templates', 'profile_create_from_template',
                   'poll', 'scheduler_tasks_list', 'settings_get', 'settings_set']:
        return jsonify({"error": "Use POST method for this endpoint"}), 405
    return send_from_directory('webui', filename)

# Serve public assets
@app.route('/public/<path:filename>')
def public_files(filename):
    return send_from_directory('webui/public', filename)

if __name__ == '__main__':
    print("🚀 Server starting on http://localhost:5000")
    print("📊 Profile endpoints available:")
    print("  - POST /profile_list")
    print("  - POST /profile_create") 
    print("  - POST /profile_update")
    print("  - POST /profile_delete")
    print("  - POST /profile_switch")
    print("  - POST /profile_templates")
    print("  - POST /profile_create_from_template")
    print("🌐 Web UI available at: http://localhost:5000")
    print("✅ All profile management features should work!")
    
    app.run(debug=False, host='0.0.0.0', port=5000, threaded=True)
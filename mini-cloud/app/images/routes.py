import os
import json
import uuid
import shutil
import subprocess
from flask import Blueprint, request, jsonify, g
from werkzeug.utils import secure_filename
from config import BASE_DIR
from app.auth.middleware import require_auth
from app.images.models import (
    create_image, get_image, list_images, delete_image,
    set_image_visibility, is_image_in_use,
)

images_bp = Blueprint('images', __name__, url_prefix='/api/v1/images')

_ALLOWED_EXTENSIONS = {'.qcow2', '.img', '.iso'}
_IMAGES_STORAGE_DIR = os.path.join(BASE_DIR, 'storage', 'images')


def _detect_format(file_path, original_ext):
    # qemu-img reads the actual file header — more reliable than the extension
    try:
        result = subprocess.run(
            ['qemu-img', 'info', '--output=json', file_path],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            return json.loads(result.stdout).get('format', 'raw')
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
        pass
    # Fallback when qemu-img is unavailable
    ext_to_fmt = {'.qcow2': 'qcow2', '.iso': 'iso', '.img': 'raw'}
    return ext_to_fmt.get(original_ext, 'raw')


@images_bp.route('', methods=['GET'])
@require_auth
def list_all():
    images = list_images(g.current_user['id'])
    # Tag each image so the UI knows which actions to show
    for img in images:
        img['is_owner'] = (img['user_id'] == g.current_user['id'])
    return jsonify({'images': images, 'count': len(images)}), 200


@images_bp.route('', methods=['POST'])
@require_auth
def upload():
    name        = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip() or None
    file        = request.files.get('file')

    if not name:
        return jsonify({'error': 'VALIDATION_ERROR', 'message': 'name is required', 'statusCode': 400}), 400
    if not file or not file.filename:
        return jsonify({'error': 'VALIDATION_ERROR', 'message': 'file is required', 'statusCode': 400}), 400

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in _ALLOWED_EXTENSIONS:
        return jsonify({
            'error': 'VALIDATION_ERROR',
            'message': f'Only {sorted(_ALLOWED_EXTENSIONS)} files are allowed',
            'statusCode': 400,
        }), 400

    image_id  = str(uuid.uuid4())
    image_dir = os.path.join(_IMAGES_STORAGE_DIR, image_id)
    os.makedirs(image_dir, exist_ok=True)

    safe_filename = secure_filename(file.filename)
    file_path = os.path.join(image_dir, safe_filename)

    try:
        file.save(file_path)
        file_size = os.path.getsize(file_path)
        fmt       = _detect_format(file_path, ext)

        create_image(image_id, g.current_user['id'], name, description, file_path, file_size, fmt)
        image = get_image(image_id)
        image['is_owner'] = True
        return jsonify({'message': 'Image uploaded', 'image': image}), 201

    except Exception as e:
        # Clean up partially saved file so storage doesn't leak
        shutil.rmtree(image_dir, ignore_errors=True)
        return jsonify({'error': 'UPLOAD_FAILED', 'message': str(e), 'statusCode': 500}), 500


@images_bp.route('/<image_id>', methods=['GET'])
@require_auth
def get_one(image_id):
    image = get_image(image_id, g.current_user['id'])
    if not image:
        return jsonify({'error': 'NOT_FOUND', 'message': 'Image not found', 'statusCode': 404}), 404
    image['is_owner'] = (image['user_id'] == g.current_user['id'])
    return jsonify({'image': image}), 200


@images_bp.route('/<image_id>', methods=['DELETE'])
@require_auth
def delete(image_id):
    from app.database import get_connection
    conn = get_connection()
    try:
        row = conn.execute(
            'SELECT * FROM images WHERE id=? AND user_id=?',
            (image_id, g.current_user['id']),
        ).fetchone()
    finally:
        conn.close()

    if not row:
        return jsonify({'error': 'NOT_FOUND', 'message': 'Image not found or you do not own it', 'statusCode': 404}), 404

    image = dict(row)

    if is_image_in_use(image_id):
        return jsonify({
            'error': 'IMAGE_IN_USE',
            'message': 'Cannot delete: image is used by one or more active instances',
            'statusCode': 409,
        }), 409

    # Remove file from disk first, then remove DB row
    image_dir = os.path.dirname(image['file_path'])
    shutil.rmtree(image_dir, ignore_errors=True)
    delete_image(image_id)

    return jsonify({'message': 'Image deleted'}), 200


@images_bp.route('/<image_id>/visibility', methods=['POST'])
@require_auth
def visibility(image_id):
    data      = request.get_json(silent=True) or {}
    is_public = data.get('is_public')

    if not isinstance(is_public, bool):
        return jsonify({'error': 'VALIDATION_ERROR', 'message': 'is_public (boolean) is required', 'statusCode': 400}), 400

    from app.database import get_connection
    conn = get_connection()
    try:
        row = conn.execute(
            'SELECT id FROM images WHERE id=? AND user_id=?',
            (image_id, g.current_user['id']),
        ).fetchone()
    finally:
        conn.close()

    if not row:
        return jsonify({'error': 'NOT_FOUND', 'message': 'Image not found or you do not own it', 'statusCode': 404}), 404

    set_image_visibility(image_id, is_public)
    label = 'public' if is_public else 'private'
    return jsonify({'message': f'Image is now {label}'}), 200

"""Private file storage helpers for homework materials and submissions."""
import os
from uuid import uuid4

from flask import current_app
from werkzeug.utils import secure_filename

ALLOWED_EXTENSIONS = {
    "7z", "csv", "doc", "docx", "jpg", "jpeg", "m4a", "mp3", "pdf",
    "png", "ppt", "pptx", "rar", "txt", "wav", "xls", "xlsx", "zip",
}
MAX_FILES_PER_UPLOAD = 10


def validate_uploads(files, required=False):
    """Return sanitized files and an error message when files are not allowed."""
    uploads = []
    for file in files:
        if not file or not file.filename:
            continue
        filename = secure_filename(file.filename)
        if not filename or len(filename) > 255:
            return [], "Tên tệp không hợp lệ."
        extension = filename.rpartition(".")[2].lower()
        if extension not in ALLOWED_EXTENSIONS:
            return [], f"Định dạng tệp .{extension or '(không có)'} chưa được hỗ trợ."
        uploads.append((file, filename))

    if required and not uploads:
        return [], "Vui lòng chọn ít nhất một tệp để nộp bài."
    if len(uploads) > MAX_FILES_PER_UPLOAD:
        return [], f"Mỗi lần chỉ được tải lên tối đa {MAX_FILES_PER_UPLOAD} tệp."
    return uploads, None


def save_upload(file):
    """Save an upload under a random private name, never using its original path."""
    stored_filename = uuid4().hex
    upload_dir = current_app.config["HOMEWORK_UPLOAD_DIR"]
    os.makedirs(upload_dir, exist_ok=True)
    file.save(os.path.join(upload_dir, stored_filename))
    return stored_filename

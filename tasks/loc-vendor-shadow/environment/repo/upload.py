from app import MAX_UPLOAD_MB


def allow(size_mb):
    return size_mb <= MAX_UPLOAD_MB

"""Pure helpers for keeping CV-to-job matching tied to current inputs."""

import hashlib


def cv_fingerprint(uploaded_cv):
    """Return a stable identity for an uploaded file, or None."""
    if uploaded_cv is None:
        return None
    content = uploaded_cv.getvalue()
    return hashlib.sha256(content).hexdigest()


def valid_cv_text(cv_text):
    return isinstance(cv_text, str) and bool(cv_text.strip())


def matching_inputs(cv_text, job_description):
    """Return the exact inputs represented by a cached analysis."""
    if not valid_cv_text(cv_text) or not isinstance(job_description, str) or not job_description.strip():
        return None
    return cv_text, job_description


def cached_match_is_current(cached_inputs, cv_text, job_description):
    return cached_inputs == matching_inputs(cv_text, job_description)

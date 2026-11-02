import os
from pathlib import Path

os.environ.setdefault("OPENAI_API_KEY", "test-key-not-real")

from streamlit.testing.v1 import AppTest


def test_manual_job_description_path_has_no_undefined_selected_job_error():
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    app = AppTest.from_file(app_path).run()

    assert not app.exception
    assert app.text_area[0].label == "Paste a job description here:"

    app.text_area[0].set_value(
        "Junior AI Engineer: Python, Git and OpenAI API experience."
    ).run()

    assert not app.exception

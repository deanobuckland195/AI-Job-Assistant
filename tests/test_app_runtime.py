import os
from pathlib import Path

os.environ.setdefault("OPENAI_API_KEY", "test-key-not-real")

from streamlit.testing.v1 import AppTest


def test_manual_job_description_path_has_no_undefined_selected_job_error():
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    app = AppTest.from_file(app_path).run()

    assert not app.exception


def test_theme_selector_switches_palette_in_current_session():
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    app = AppTest.from_file(app_path).run()

    theme_selector = next(
        widget for widget in app.selectbox if widget.label == "Colour theme"
    )
    assert theme_selector.options == [
        "Professional Light",
        "Professional Dark",
        "Navy Blue",
    ]

    theme_selector.set_value("Professional Dark").run()
    assert not app.exception
    assert next(widget for widget in app.selectbox if widget.label == "Colour theme").value == "Professional Dark"

    theme_selector.set_value("Navy Blue").run()
    assert not app.exception
    assert next(widget for widget in app.selectbox if widget.label == "Colour theme").value == "Navy Blue"
    assert app.text_area[0].label == "Paste a job description here:"

    app.text_area[0].set_value(
        "Junior AI Engineer: Python, Git and OpenAI API experience."
    ).run()

    assert not app.exception

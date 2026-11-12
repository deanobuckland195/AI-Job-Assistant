"""Standalone offline visual check: run with a Python that has Playwright installed.

Uses the project's .venv for Streamlit, a temporary synthetic SQLite database,
and localhost-only browser requests. Never opens the user's database.
Set PLAYWRIGHT_BROWSERS_PATH if using an existing browser cache.
Usage: python tests/browser_dashboard_check.py --artifacts /tmp/job-dashboard-qa
"""
import argparse
import os
import re
from pathlib import Path
import socket
import sqlite3
import subprocess
import tempfile
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def run(artifacts):
    from playwright.sync_api import sync_playwright, expect

    artifacts.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='job-dashboard-qa-') as directory:
        database = Path(directory) / 'synthetic.sqlite3'
        env = dict(os.environ, AI_JOB_ASSISTANT_DATABASE=str(database), OPENAI_API_KEY='', PYTHONDONTWRITEBYTECODE='1')
        python = str(ROOT / '.venv/bin/python')
        subprocess.run([python, '-c', '''
import os
from job_assistant import applications, storage, interview_store, roadmap_store
with storage.database(os.environ['AI_JOB_ASSISTANT_DATABASE']) as c:
    applications.create_application(c, company='Synthetic Robotics', role='AI Engineering Apprentice', status='interviewing', next_action='Prepare project walkthrough')
    interview_store.start_session(c, 'ai-engineering-apprentice', title='Synthetic interview practice')
    roadmap_store.create_roadmap(c, 'ai-engineering-apprentice', 'Python, Git', 4, title='AI Engineering learning plan')
'''], cwd=ROOT, env=env, check=True)
        def dump():
            with sqlite3.connect(database) as connection:
                return list(connection.iterdump())
        before = dump()
        # Test-only page for real disabled widgets; production pages are untouched.
        entrypoint = Path(directory) / 'visual_probe.py'
        entrypoint.write_text(f"import sys\nsys.path.insert(0, {str(ROOT)!r})\n" + """
import streamlit as st
from job_assistant.dashboard_ui import run
from job_assistant.dashboard_theme import DARK_STYLE
if st.query_params.get('theme_probe'):
    st.markdown(DARK_STYLE, unsafe_allow_html=True)
    st.title('Disabled controls')
    st.caption('Readable secondary text')
    st.button('Primary action preview', type='primary')
    st.progress(0.6, text='Visual progress preview')
    st.text_input('Disabled text', 'Readable value', disabled=True)
    st.text_area('Disabled notes', 'Readable notes', disabled=True)
    st.selectbox('Disabled choice', ['Readable choice'], disabled=True)
    st.multiselect('Disabled multi', ['Readable choice'], default=['Readable choice'], disabled=True)
    st.date_input('Disabled date', disabled=True)
    st.number_input('Disabled number', value=4, disabled=True)
else:
    run()
""")
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        url = f'http://127.0.0.1:{port}'
        with (artifacts / 'server.log').open('w') as log:
            server = subprocess.Popen([python, '-m', 'streamlit', 'run', str(entrypoint), f'--server.port={port}', '--server.address=127.0.0.1', '--server.fileWatcherType=none'], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
            try:
                for _ in range(100):
                    try:
                        with urlopen(url + '/_stcore/health', timeout=1):
                            break
                    except OSError:
                        time.sleep(.1)
                else:
                    raise AssertionError('Local test server did not start')
                with sync_playwright() as p:
                    browser = p.chromium.launch()
                    try:
                        for width in (390, 768, 1440):
                            context = browser.new_context(viewport={'width':width,'height':1000}, reduced_motion='reduce')
                            context.route('**/*', lambda r: r.continue_() if r.request.url.startswith(url + '/') else r.abort())
                            page = context.new_page()
                            errors = []
                            page.on('pageerror', lambda e: errors.append(str(e)))
                            page.goto(url)
                            expect(page.get_by_role('heading', name='Your applications', exact=True)).to_be_visible()
                            for route in ('Applications', 'Add application', 'Interview Practice', 'Skills Roadmap'):
                                sidebar = page.get_by_test_id('stSidebar')
                                if not sidebar.bounding_box() or sidebar.bounding_box()['x'] < 0:
                                    page.get_by_role('button', name='Expand sidebar', exact=True).click()
                                sidebar.get_by_text(route, exact=True).click()
                                heading = {'Applications':'Your applications', 'Add application':'New application', 'Interview Practice':'Start a practice session', 'Skills Roadmap':'Plan your learning'}[route]
                                expect(page.get_by_role('heading', name=heading, exact=True)).to_be_visible()
                                if width <= 768:
                                    page.get_by_role('button', name='Collapse sidebar', exact=True).click()
                                expect(page.get_by_test_id('stApp')).to_have_css('background-color','rgb(7, 6, 25)')
                                expect(page.get_by_test_id('stApp')).to_have_css('background-image','none')
                                expect(page.get_by_test_id('stAppViewContainer')).to_have_css('background-color','rgb(7, 6, 25)')
                                expect(sidebar).to_have_css('background-color','rgb(16, 13, 44)')
                                expect(page.get_by_test_id('stMain')).to_have_css('background-color','rgba(0, 0, 0, 0)')
                                assert 'linear-gradient' in page.get_by_test_id('stHeader').evaluate('el=>getComputedStyle(el).backgroundImage')
                                # Every visible native control is outlined before focus.
                                roots = page.locator('[data-testid="stTextInputRootElement"], [data-testid="stTextAreaRootElement"], [data-testid="stNumberInputContainer"], .stSelectbox [role="group"], .stMultiSelect div[role="group"], [data-testid="stDateInputField"]')
                                for root in roots.all():
                                    if root.is_visible():
                                        expect(root).to_have_css('background-color','rgb(44, 36, 64)')
                                        expect(root).to_have_css('border-top-color','rgb(164, 122, 183)')
                                        expect(root).to_have_css('border-top-width','1px')
                                if route == 'Add application':
                                    status = page.get_by_role('combobox', name='Status', exact=True)
                                    status.click()
                                    expect(page.get_by_role('listbox')).to_be_visible()
                                    page.keyboard.press('Escape')
                                    company = page.get_by_role('textbox', name='Company *', exact=True)
                                    company.focus()
                                    expect(company.locator('..')).to_have_css('border-top-color','rgb(211, 161, 255)')
                                    company.press('Tab')
                                    expect(company.locator('..')).to_have_css('border-top-color','rgb(164, 122, 183)')
                                    date = page.get_by_test_id('stDateInputField').first
                                    date.get_by_role('spinbutton').first.focus()
                                    expect(date).to_have_css('border-top-color','rgb(211, 161, 255)')
                                    page.get_by_test_id('stDateInputCalendarButton').first.click()
                                    expect(page.get_by_role('dialog')).to_be_visible()
                                    page.keyboard.press('Escape')
                                if route == 'Applications':
                                    expect(page.get_by_role('heading',name='Your career, moving forward.',exact=True)).to_be_visible()
                                    hero = page.locator('.st-key-dashboard_hero')
                                    expect(hero).to_have_css('background-image', re.compile('linear-gradient'))
                                    add_action = hero.get_by_role('button',name='Add application',exact=True)
                                    add_action.focus()
                                    add_action.press('Enter')
                                    expect(page.get_by_role('heading',name='New application',exact=True)).to_be_visible()
                                    # Returning through the native sidebar preserves the same existing route.
                                    if not sidebar.bounding_box() or sidebar.bounding_box()['x'] < 0:
                                        page.get_by_role('button',name='Expand sidebar',exact=True).click()
                                    sidebar.get_by_text('Applications',exact=True).click()
                                    if width <= 768:
                                        page.get_by_role('button',name='Collapse sidebar',exact=True).click()
                                    expect(page.locator('.st-key-application_listing')).to_have_css('background-color','rgba(0, 0, 0, 0)')
                                    search = page.get_by_role('textbox',name='Search applications',exact=True)
                                    assert search.evaluate("el=>getComputedStyle(el,'::placeholder').color") == 'rgb(219, 197, 233)'
                                    expect(page.locator('.st-key-application_grid')).to_contain_text('Synthetic Robotics')
                                    page.get_by_role('tab',name='Table view',exact=True).click()
                                    grid = page.get_by_test_id('stDataFrame')
                                    expect(grid.locator('canvas').first).to_be_visible()
                                    grid.hover()
                                    grid.get_by_role('button',name='Fullscreen',exact=True).click(trial=True)
                                    page.get_by_role('tab',name='Application cards',exact=True).click()
                                if route == 'Interview Practice':
                                    answer = page.get_by_role('textbox',name='Your practice answer',exact=True)
                                    answer.fill('Situation: I built a synthetic Python project at college. Task: I needed to validate input rows. Action: I wrote a parser and tested missing values. Result: the checks caught invalid rows and I documented the limitations.')
                                    page.get_by_role('button',name='Review offline feedback',exact=True).click()
                                    expect(page.get_by_role('heading',name='Answer feedback',exact=True)).to_be_visible()
                                    expect(page.get_by_role('checkbox',name='I consent to sending this question and answer to OpenAI for this request')).not_to_be_checked()
                                    expect(page.locator('.st-key-interview_workspace')).to_be_visible()
                                    # No saved answer is created by this visual review.
                                if route == 'Skills Roadmap':
                                    expect(page.get_by_role('heading',name='Build Your Career Roadmap',exact=True)).to_be_visible()
                                    expect(page.locator('.st-key-saved_milestone_grid')).to_contain_text('WEEK 01')
                                    first = page.locator('.st-key-saved_milestone_card_1').bounding_box()
                                    second = page.locator('.st-key-saved_milestone_card_2').bounding_box()
                                    if width == 390:
                                        assert abs(first['x'] - second['x']) < 2 and second['y'] > first['y']
                                    else:
                                        assert second['x'] > first['x'] and abs(first['y'] - second['y']) < 2
                                    expect(page.get_by_role('heading',name='Your learning progress',exact=True)).to_be_visible()
                                    expect(page.get_by_role('progressbar')).to_be_visible()
                                    page.get_by_text('Delete skills roadmap',exact=True).click()
                                    expect(page.get_by_role('button',name='Confirm roadmap deletion')).to_be_disabled()
                                assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth+2'), (route,width)
                                assert not page.get_by_test_id('stException').count()
                                if route == 'Skills Roadmap':
                                    page.locator('.st-key-saved_milestone_grid').screenshot(path=str(artifacts / f'milestone-cards-{width}.png'))
                                if route == 'Interview Practice':
                                    page.locator('.st-key-interview_workspace').screenshot(path=str(artifacts / f'interview-question-{width}.png'))
                                page.locator('.st-key-dashboard_hero' if route == 'Applications' else '.st-key-page_intro').click()
                                page.get_by_test_id('stMain').evaluate('el=>el.scrollTop=0')
                                page.screenshot(path=str(artifacts / f'{route.lower().replace(" ","-")}-{width}.png'),full_page=True)
                            assert not errors, errors
                            page.goto(url + '/?theme_probe=1')
                            expect(page.get_by_role('heading',name='Disabled controls',exact=True)).to_be_visible()
                            expect(page.get_by_role('button', name='Primary action preview')).to_have_css('background-image', re.compile('linear-gradient'))
                            expect(page.get_by_role('progressbar').locator(':scope > div')).to_have_css('background-image', re.compile('linear-gradient'))
                            expect(page.get_by_text('Readable secondary text',exact=True)).to_have_css('color','rgb(213, 191, 231)')
                            for field in page.locator('input:disabled,textarea:disabled').all():
                                if field.is_visible():
                                    expect(field).to_have_css('color','rgb(212, 193, 224)')
                                    expect(field).to_have_css('opacity','1')
                            for root in page.locator('[data-testid="stTextInputRootElement"], [data-testid="stTextAreaRootElement"], [data-testid="stNumberInputContainer"], .stSelectbox [role="group"], .stMultiSelect div[role="group"], [data-testid="stDateInputField"]').all():
                                expect(root).to_have_css('background-color','rgb(43, 25, 56)')
                                expect(root).to_have_css('border-top-color','rgb(141, 113, 158)')
                            for segment in page.get_by_role('spinbutton').all():
                                expect(segment).to_have_css('color','rgb(212, 193, 224)')
                            expect(page.locator('.stMultiSelect [data-tag] span')).to_have_css('color','rgb(212, 193, 224)')
                            page.screenshot(path=str(artifacts / f'disabled-controls-{width}.png'),full_page=True)
                            context.close()
                            print(f'PASS: four pages, control visibility, focus, offline feedback, progress and layout at {width}px', flush=True)
                    finally:
                        browser.close()
                assert dump() == before, 'Visual checks changed saved records'
                print('PASS: synthetic database unchanged; all external browser requests blocked', flush=True)
            finally:
                server.terminate()
                server.wait(timeout=10)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path, required=True)
    run(parser.parse_args().artifacts)

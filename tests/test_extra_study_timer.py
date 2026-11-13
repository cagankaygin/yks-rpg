"""Existing study-timer integration for Extra sessions; cloud calls are mocked."""
import argparse
import copy
import functools
import http.server
import json
import shutil
import threading
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--supabase-js', type=Path, help='Optional TLS-verified local browser library')
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
cdn = 'https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2'
library = args.supabase_js.read_bytes() if args.supabase_js else urllib.request.urlopen(cdn, timeout=30).read()
KEY, TOKEN = 'yks-xp-final-v1', 'synthetic-owner-test-only-1234567890'
DAY, WEEK = '2026-11-13', '2026-11-09'
NOW = datetime(2026, 11, 13, 6, tzinfo=timezone.utc)
fixture = {
    'checks': {'2026-10-05|tyt': True, '2026-10-16|extra:paragraph': True, '2026-11-12|geo': True},
    'rests': {}, 'purchases': 1, 'refunds': 0, 'spentRests': 0,
    'rewardBuys': [{'type': 'burger', 'date': '2026-10-20T12:00:00Z', 'price': 800, 'couponUsed': False}],
    'weekPlans': {WEEK: {DAY: ['bio', 'mathStudy'], '2026-11-12': ['geo']}},
    'planNotes': {DAY: {'bio': 'Hücrelerden 2 test'}},
    'checkins': {'2026-11-12': {'load': 3, 'satisfaction': 4, 'note': 'Eski kayıt'}},
    'settings': {'examDate': '2027-06-19'},
    'studyTimer': {'running': None, 'sessions': [{'id': 'historical-session', 'day': '2026-11-12',
        'startedAt': '2026-11-12T06:00:00Z', 'endedAt': '2026-11-12T06:30:00Z',
        'seconds': 1800, 'label': 'Eski ana ders', 'taskKey': 'geo'}]},
    'lockIn': {'days': {'2026-11-12': {'env': 'home', 'active': False, 'startedAt': ''}}},
}

class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_): pass

class Backend:
    def __init__(self): self.state, self.calls = {}, []
    def request(self, route):
        name, body = route.request.url.rsplit('/', 1)[-1], route.request.post_data_json
        self.calls.append(name)
        if name == 'get_yks_rpg_owner_state' and body['raw_owner_token'] == TOKEN:
            value = [{'state': self.state, 'updated_at': '2026-11-13T06:00:00Z'}]
        elif name == 'save_yks_rpg_state' and body['raw_owner_token'] == TOKEN:
            self.state = copy.deepcopy(body['new_state']); value = '2026-11-13T06:00:00Z'
        elif name == 'get_yks_rpg_coach_state':
            value = [{'state': self.state, 'updated_at': '2026-11-13T06:00:00Z'}]
        else: raise AssertionError('Unexpected RPC: ' + name)
        route.fulfill(json=copy.deepcopy(value))

server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=str(root)))
threading.Thread(target=server.serve_forever, daemon=True).start()
url, backend, contexts, errors = f'http://127.0.0.1:{server.server_port}/', Backend(), [], []
accept_dialog = True

def context(browser, initial=None, owner=False, coach=False, now=NOW):
    ctx = browser.new_context(viewport={'width': 360, 'height': 900}, timezone_id='Europe/Istanbul', accept_downloads=True, reduced_motion='reduce')
    contexts.append(ctx)
    ctx.route(cdn, lambda route: route.fulfill(body=library, content_type='application/javascript'))
    ctx.route('**/rest/v1/rpc/*', backend.request)
    if initial is not None:
        ctx.add_init_script(f"if(!localStorage.getItem('{KEY}'))localStorage.setItem('{KEY}',{json.dumps(json.dumps(initial))})")
    if owner: ctx.add_init_script(f"localStorage.setItem('yks-rpg-owner-token-v1',{json.dumps(TOKEN)})")
    page = ctx.new_page(); page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('dialog', lambda dialog: dialog.accept() if accept_dialog else dialog.dismiss())
    page.clock.install(time=now); page.clock.pause_at(now+timedelta(seconds=1))
    page.goto(url+('#coach=synthetic-coach-test' if coach else ''), wait_until='networkidle')
    return page

def row(page, key): return page.locator(f'.extraStudy[data-study-extra="{key}"]')
def control(page, key, action): return row(page, key).locator(f'[data-extra-timer-action="{action}"]')
def advance(page, seconds): page.clock.run_for(round(seconds*1000))
def extra_open(page):
    if not page.locator('#extraPanel').evaluate('(el)=>el.open'): page.locator('#extraPanel summary').click()
def no_overflow(page): assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
def non_timer(page): return page.evaluate('Object.fromEntries(Object.entries(state).filter(([key])=>key!=="studyTimer"))')
def total(page): return page.evaluate('totals().earned')
def current_time(page): return datetime.fromisoformat(page.evaluate('new Date().toISOString()').replace('Z', '+00:00'))

try:
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=shutil.which('chromium') or shutil.which('chromium-browser'), headless=True, args=['--no-sandbox'])
        page = context(browser, initial=fixture); extra_open(page)
        assert page.evaluate('KEY') == KEY
        assert page.evaluate('state.studyTimer.sessions') == fixture['studyTimer']['sessions']
        assert page.locator('.extraStudy [data-extra-timer-action="start"]').count() == page.evaluate('EXTRA_KEYS.length')
        before, earned = non_timer(page), total(page)
        control(page, 'bio', 'start').click()
        assert page.evaluate('studyRunning().taskKey') == 'extra:bio'
        assert not page.evaluate('isDone(today(),extraKey("bio"))')
        assert non_timer(page) == before and total(page) == earned
        expect(page.locator('#studyTimerStart')).to_be_disabled()
        expect(control(page, 'physics', 'start')).to_be_disabled()
        run = page.evaluate('studyRunning()')
        page.evaluate('startStudyTimerForTask("mathStudy","Ana ders");startExtraStudyTimer("physics")')
        assert page.evaluate('studyRunning()') == run
        advance(page, 10)
        assert page.evaluate('runningStudySeconds()') == 10
        expect(row(page, 'bio')).to_contain_text('00:00:10')
        expect(page.locator('#studyDayTotal')).to_have_text('10 sn')
        expect(page.locator('#weeklyStudyTotal')).to_have_text('30 dk')
        assert page.evaluate('studyDaySeconds(today())') == 10
        control(page, 'bio', 'pause').click(); advance(page, 7)
        assert page.evaluate('runningStudySeconds()') == 10
        expect(row(page, 'bio')).to_contain_text('Molada')
        page.reload(wait_until='networkidle'); extra_open(page)
        assert page.evaluate('runningStudySeconds()') == 10
        expect(control(page, 'bio', 'pause')).to_have_text('▶ Devam Et')
        control(page, 'bio', 'pause').click(); advance(page, 5)
        control(page, 'bio', 'stop').click()
        assert page.evaluate('studyRunning()') is None
        assert page.evaluate('state.studyTimer.sessions.at(-1).taskKey') == 'extra:bio'
        assert page.evaluate('state.studyTimer.sessions.at(-1).seconds') == 15
        assert page.evaluate('studyTaskSeconds(today(),"extra:bio")') == 15
        assert page.evaluate('studyDaySeconds(today())') == 15
        assert page.evaluate('datesBetween(monday(today()),add(monday(today()),6)).reduce((n,d)=>n+studyDaySeconds(d),0)') == 1815
        assert non_timer(page) == before and total(page) == earned
        print('PASS: every Extra gets the shared timer; one running main/Extra only; start/pause/resume/finish, excluded pause time, paused reload, extra taskKey and daily/weekly totals; zero XP/state side effects.')

        page.locator('#extraTasks input[data-extra="bio"]').click()
        assert total(page) == earned + 90
        expect(page.locator('#completedExtraTasks')).to_contain_text('➕ EK')
        control(page, 'bio', 'start').click(); advance(page, 4); control(page, 'bio', 'stop').click()
        assert total(page) == earned + 90
        assert page.evaluate('studyTaskSeconds(today(),"extra:bio")') == 19
        page.locator('#completedExtraTasks input[data-extra="bio"]').click()
        assert total(page) == earned
        page.locator('#extraTasks input[data-extra="bio"]').click()
        assert total(page) == earned + 90
        # A main timer and same-subject extra remain separate; unrelated checks never finish it.
        page.locator('#studyTimerStart').click(); page.locator('[data-study-task="bio"]').click(); advance(page, 6)
        page.locator('#extraTasks input[data-extra="problem"]').click()
        assert page.evaluate('studyRunning().taskKey') == 'bio'
        assert page.evaluate('runningStudySeconds()') == 6
        before_main = total(page)
        page.locator('#tasks .task').filter(has=page.get_by_text('TYT Biyoloji', exact=True)).locator('input').click()
        assert page.evaluate('studyRunning()') is None
        assert page.evaluate('state.studyTimer.sessions.at(-1).taskKey') == 'bio'
        assert page.evaluate('state.studyTimer.sessions.at(-1).seconds') == 6
        assert total(page) == before_main + 90
        assert page.evaluate('studyTaskSeconds(today(),"extra:bio")') == 19
        assert page.evaluate('studyTaskSeconds(today(),"bio")') == 6
        # Cancel leaves both clock and checkbox intact; accept stops the matching timer once.
        control(page, 'geo', 'start').click(); advance(page, 3)
        session_count, xp = page.evaluate('state.studyTimer.sessions.length'), total(page)
        accept_dialog = False; page.locator('#extraTasks input[data-extra="geo"]').click()
        assert page.evaluate('studyRunning().taskKey') == 'extra:geo'
        assert not page.evaluate('isDone(today(),extraKey("geo"))')
        assert page.evaluate('state.studyTimer.sessions.length') == session_count and total(page) == xp
        accept_dialog = True; page.locator('#extraTasks input[data-extra="geo"]').click()
        assert page.evaluate('studyRunning()') is None
        assert page.evaluate('state.studyTimer.sessions.length') == session_count + 1
        assert page.evaluate('state.studyTimer.sessions.at(-1).seconds') == 3
        assert total(page) == xp + 125
        no_overflow(page)
        print('PASS: completion gives Extra XP exactly once; repeat timed sessions and uncheck/recheck do not duplicate XP; main/Extra subject time stays separate; only matching checkbox stops a clock and cancellation preserves it.')

        # The global picker also starts extras; global and row controls operate the same run.
        page.locator('#studyTimerStart').click(); page.locator('[data-study-task="extra:chem"]').click(); advance(page, 2)
        page.locator('#studyTimerPause').click(); advance(page, 5)
        assert page.evaluate('runningStudySeconds()') == 2
        control(page, 'chem', 'pause').click(); advance(page, 2); page.locator('#studyTimerStop').click()
        assert page.evaluate('state.studyTimer.sessions.at(-1).taskKey') == 'extra:chem'
        assert page.evaluate('state.studyTimer.sessions.at(-1).seconds') == 4
        assert not page.evaluate('isDone(today(),extraKey("chem"))')
        control(page, 'physics', 'start').click(); advance(page, 8)
        running = page.evaluate('studyRunning()'); page.reload(wait_until='networkidle'); extra_open(page)
        assert page.evaluate('studyRunning()') == running
        assert page.evaluate('runningStudySeconds()') == 8
        expect(control(page, 'mathStudy', 'start')).to_be_disabled()
        control(page, 'physics', 'stop').click()
        assert page.evaluate('studyDaySeconds(today(),false)') == 40
        assert page.evaluate('studyDaySeconds("2026-11-12",false)') == 1800
        assert page.evaluate('studyTaskSeconds(today(),"extra:physics")') == 8
        for day in ['2026-11-12', '2026-11-14']:
            page.locator('#date').fill(day); page.locator('#date').dispatch_event('change')
            expect(control(page, 'bio', 'start')).to_be_disabled()
            page.evaluate('startExtraStudyTimer("bio")'); assert page.evaluate('studyRunning()') is None
        page.locator('#date').fill(DAY); page.locator('#date').dispatch_event('change')
        assert page.evaluate('studyDaySeconds(today())') == 40
        page.locator('[data-tab="backupTab"]').click()
        with page.expect_download() as info: page.locator('#export').click()
        backup = json.loads(Path(info.value.path()).read_text()); snapshot = page.evaluate('state')
        assert backup['state'] == snapshot
        page.locator('#import').set_input_files({'name': 'timer.json', 'mimeType': 'application/json', 'buffer': json.dumps(backup).encode()})
        assert page.evaluate('state') == snapshot
        page.reload(wait_until='networkidle'); assert page.evaluate('state') == snapshot
        assert snapshot['studyTimer']['sessions'][0] == fixture['studyTimer']['sessions'][0]
        for key, value in fixture['checks'].items(): assert snapshot['checks'][key] == value
        no_overflow(page)
        print('PASS: shared picker/global pause/row resume/global finish; running reload; exact aggregate 40s today + 1800s historical, past/future locks, original sessions/checks, JSON round trip and reload.')

        # Extra-only days work in the shared picker; old unassigned paused timers remain valid.
        empty = context(browser, initial={'checks': {}, 'rests': {}}, now=current_time(page))
        assert empty.locator('#tasks .task').count() == 0
        empty.locator('#studyTimerStart').click()
        empty.locator('[data-study-task="extra:paragraph"]').click(); advance(empty, 1)
        empty.locator('#studyTimerStop').click()
        assert empty.evaluate('state.studyTimer.sessions.at(-1).taskKey') == 'extra:paragraph'
        assert total(empty) == 0
        old_active = copy.deepcopy(fixture)
        old_active['studyTimer']['running'] = {'day': DAY, 'startedAt': (NOW-timedelta(seconds=20)).isoformat(),
            'pausedAt': (NOW-timedelta(seconds=5)).isoformat(), 'pausedSeconds': 3, 'label': 'Eski serbest oturum', 'taskKey': ''}
        recovered = context(browser, initial=old_active)
        assert recovered.evaluate('runningStudySeconds()') == 12
        recovered.reload(wait_until='networkidle'); advance(recovered, 4)
        assert recovered.evaluate('runningStudySeconds()') == 12
        recovered.locator('#studyTimerStop').click()
        assert recovered.evaluate('state.studyTimer.sessions.at(-1).seconds') == 12
        assert recovered.evaluate('state.studyTimer.sessions.at(-1).label') == 'Eski serbest oturum'
        assert recovered.evaluate('state.studyTimer.sessions.at(-1).taskKey') == ''
        print('PASS: Extra-only days use the existing picker without a main plan; legacy unassigned paused runs retain their net time, label and session data.')

        backend.state = copy.deepcopy(snapshot)
        owner = context(browser, owner=True, now=current_time(page)); extra_open(owner)
        xp = total(owner)
        control(owner, 'bio', 'start').click(); advance(owner, 2); control(owner, 'bio', 'stop').click(); advance(owner, 0.6)
        owner.wait_for_function("document.getElementById('cloudStatus').textContent==='Kaydedildi'")
        assert backend.state['studyTimer'] == owner.evaluate('state.studyTimer')
        assert total(owner) == xp
        second = context(browser, owner=True, now=current_time(owner))
        assert second.evaluate('state.studyTimer') == backend.state['studyTimer']
        assert second.evaluate('studyTaskSeconds(today(),"extra:bio")') == 21
        control(owner, 'chem', 'start').click(); advance(owner, 1)
        owner.wait_for_function("document.getElementById('cloudStatus').textContent==='Kaydedildi'")
        assert backend.state['studyTimer']['running']['taskKey'] == 'extra:chem'
        second.reload(wait_until='networkidle')
        active = second.evaluate('studyRunning()')
        second.evaluate('startExtraStudyTimer("geo")')
        assert second.evaluate('studyRunning()') == active
        coach = context(browser, coach=True, now=current_time(owner)); extra_open(coach)
        assert coach.locator('.extraStudyTimer button:enabled').count() == 0
        expect(control(coach, 'chem', 'pause')).to_be_visible()
        expect(control(coach, 'chem', 'stop')).to_be_disabled()
        before = coach.evaluate('state')
        coach.evaluate('startExtraStudyTimer("bio");toggleStudyTimerPause();stopStudyTimer()')
        assert coach.evaluate('state') == before
        assert coach.evaluate('studyTaskSeconds(today(),"extra:bio")') == 21
        no_overflow(owner); no_overflow(coach)
        print('PASS: existing state RPCs sync extra taskKey/sessions to a second device; no new state schema/table/key, coach readonly and 360px overflow checks.')
        assert not errors, errors
        browser.close()
finally:
    for ctx in contexts:
        try: ctx.close()
        except Exception: pass
    server.shutdown()

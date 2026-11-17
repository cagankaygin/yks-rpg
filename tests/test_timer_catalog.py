"""All-course selection over the existing study timer. No real student/cloud data is used."""
import argparse, copy, functools, http.server, json, shutil, threading, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--supabase-js', type=Path)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
cdn = 'https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2'
library = args.supabase_js.read_bytes() if args.supabase_js else urllib.request.urlopen(cdn, timeout=30).read()
KEY, TOKEN = 'yks-xp-final-v1', 'synthetic-timer-catalog-owner-only-1234567'
DAY, WEEK = '2026-11-17', '2026-11-16'
NOW = datetime(2026, 11, 17, 6, tzinfo=timezone.utc)
fixture = {
    'checks': {'2026-10-05|tyt': True, '2026-10-16|paragraph': True, '2026-11-16|geo': True},
    'rests': {}, 'purchases': 1, 'refunds': 0, 'spentRests': 0,
    'rewardBuys': [{'type': 'burger', 'date': '2026-10-20T12:00:00Z', 'price': 800, 'couponUsed': False}],
    'weekPlans': {WEEK: {DAY: [], '2026-11-16': ['geo']}},
    'planNotes': {'2026-11-16': {'geo': 'Eski plan notu'}},
    'chestClaims': {'2026-11-09': {'tier': 'Gold', 'reward': 200, 'date': '2026-11-15T06:00:00Z'}},
    'checkins': {'2026-11-16': {'load': 3, 'satisfaction': 4, 'note': 'Eski kayıt'}},
    'settings': {'examDate': '2027-06-19'},
    'studyTimer': {'running': None, 'sessions': [
        {'id': 'old-geo', 'day': '2026-11-16', 'startedAt': '2026-11-16T06:00:00Z', 'endedAt': '2026-11-16T06:30:00Z', 'seconds': 1800, 'label': 'Geometri', 'taskKey': 'geo'},
        {'id': 'old-ayt', 'day': '2026-11-16', 'startedAt': '2026-11-16T07:00:00Z', 'endedAt': '2026-11-16T07:01:00Z', 'seconds': 60, 'label': 'AYT Fizik', 'taskKey': 'aytPhysics'},
        {'id': 'unassigned', 'day': '2026-11-16', 'startedAt': '2026-11-16T08:00:00Z', 'endedAt': '2026-11-16T08:00:05Z', 'seconds': 5, 'label': 'Eski serbest çalışma', 'taskKey': ''},
    ]},
}

class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_): pass
server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=str(root)))
threading.Thread(target=server.serve_forever, daemon=True).start()
url = f'http://127.0.0.1:{server.server_port}/'
cloud, calls, contexts, errors = copy.deepcopy(fixture), [], [], []

def rpc(route):
    global cloud
    name, body = route.request.url.rsplit('/', 1)[-1], route.request.post_data_json
    calls.append(name)
    if name == 'get_yks_rpg_owner_state' and body['raw_owner_token'] == TOKEN:
        value = [{'state': cloud, 'updated_at': DAY+'T06:00:00Z'}]
    elif name == 'save_yks_rpg_state' and body['raw_owner_token'] == TOKEN:
        cloud = copy.deepcopy(body['new_state']); value = DAY+'T06:00:00Z'
    elif name == 'get_yks_rpg_coach_state': value = [{'state': cloud, 'updated_at': DAY+'T06:00:00Z'}]
    else: raise AssertionError('Unexpected RPC: '+name)
    route.fulfill(json=copy.deepcopy(value))

def context(browser, initial=None, owner=False, coach=False):
    ctx = browser.new_context(viewport={'width': 360, 'height': 900}, timezone_id='Europe/Istanbul', accept_downloads=True, reduced_motion='reduce')
    contexts.append(ctx)
    ctx.route(cdn, lambda r: r.fulfill(body=library, content_type='application/javascript'))
    ctx.route('**/rest/v1/rpc/*', rpc)
    if initial is not None: ctx.add_init_script(f"if(!localStorage.getItem('{KEY}'))localStorage.setItem('{KEY}',{json.dumps(json.dumps(initial))})")
    if owner: ctx.add_init_script(f"localStorage.setItem('yks-rpg-owner-token-v1',{json.dumps(TOKEN)})")
    page = ctx.new_page(); page.on('pageerror', lambda e: errors.append(str(e))); page.on('dialog', lambda d: d.accept())
    page.clock.install(time=NOW); page.clock.pause_at(NOW+timedelta(seconds=1))
    page.goto(url+('#coach=synthetic-timer-catalog' if coach else ''), wait_until='networkidle')
    return page

def advance(page, seconds): page.clock.run_for(seconds*1000)
def no_overflow(page): assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
def start(page, key):
    page.locator('#studyTimerStart').click()
    no_overflow(page)
    page.locator(f'[data-study-task="{key}"]').click()
def non_timer(page): return page.evaluate('Object.fromEntries(Object.entries(state).filter(([key])=>key!=="studyTimer"))')
def gameplay(page): return page.evaluate('({xp:totals(),rank:dayRank(today()),pct:completionPct(today()),boss:boss(),streak:currentAndBestStreak(),quest:weekQuestStatus(monday(today()))})')
def choose(page, day):
    page.locator('#date').fill(day); page.locator('#date').dispatch_event('change')

try:
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=shutil.which('chromium') or shutil.which('chromium-browser'), headless=True, args=['--no-sandbox'])
        page = context(browser, fixture)
        expect(page).to_have_title('YKS RPG V3.33')
        expect(page.locator('.version')).to_have_text('V3.33')
        assert page.evaluate('KEY') == KEY
        assert page.evaluate('state.studyTimer.sessions') == fixture['studyTimer']['sessions']
        state_before, mechanics = non_timer(page), gameplay(page)
        assert page.locator('#tasks .task').count() == 0
        page.locator('#studyTimerStart').click()
        keys = page.locator('[data-study-task]').evaluate_all('(els)=>els.map(el=>el.dataset.studyTask)')
        expected = {'extra:paragraph','extra:problem','extra:mathStudy','extra:geo','extra:physics','extra:chem','extra:bio','extra:turkishStudy','extra:grammar','extra:geoTYT','extra:hist',
                    'tytSocial','tytScience','aytMath','aytPhysics','aytChem','aytBio','extra:mat','extra:tr','extra:generalExam','extra:dailyAnalysis','extra:generalExamAnalysis','tyt',
                    'anGeo','anPhysics','anChem','anBio','anProblem','anMath','anGeoTYT','anHist','anGrammar'}
        assert expected.issubset(keys), expected-set(keys)
        assert len(keys) == len(set(keys))
        for label in ['TYT DERSLERİ','AYT DERSLERİ','BRANŞ DENEMELERİ','GENEL DENEMELER','ANALİZ GÖREVLERİ']:
            expect(page.locator('#studyTimerTaskChoices')).to_contain_text(label)
        no_overflow(page)
        page.locator('[data-study-task="aytPhysics"]').click()
        advance(page, 65); page.locator('#studyTimerPause').click(); advance(page, 10)
        assert page.evaluate('runningStudySeconds()') == 65
        run = page.evaluate('studyRunning()')
        page.evaluate('startStudyTimerForTask("aytMath","AYT Matematik")')
        assert page.evaluate('studyRunning()') == run
        expect(page.locator('#studyTimerStart')).to_be_disabled()
        page.reload(wait_until='networkidle')
        assert page.evaluate('studyRunning()') == run
        page.locator('#studyTimerPause').click(); advance(page, 5); page.locator('#studyTimerStop').click()
        session = page.evaluate('state.studyTimer.sessions.at(-1)')
        assert session['taskKey'] == 'aytPhysics' and session['label'] == 'AYT Fizik' and session['day'] == DAY and session['seconds'] == 70
        assert page.evaluate('studyTaskSeconds(today(),"aytPhysics")') == 70
        assert page.evaluate('studyDaySeconds(today())') == 70
        expect(page.locator('#studyDayTotal')).to_have_text('1 dk')
        expect(page.locator('#weeklyStudyTotal')).to_have_text('32 dk')
        page.locator('#studySubjectSummary summary').click()
        row = page.locator('#studySubjectTimes tr').filter(has=page.get_by_text('AYT Fizik', exact=True))
        expect(row).to_contain_text('00:01:10'); expect(row).to_contain_text('00:02:10')
        assert non_timer(page) == state_before and gameplay(page) == mechanics
        print('PASS: full existing TYT/AYT, branch/general exams and analysis catalog without a plan; pause/resume/reload, one clock, exact subject/day/week totals; no plan/check/XP/Rank/Boss/streak/quest mutation.')

        # Actual UI starts from each family, including legacy analysis IDs and Extra task keys.
        for key in ['aytMath','aytChem','aytBio','tytSocial','tytScience','extra:mathStudy','extra:mat','extra:tr','extra:generalExam','extra:generalExamAnalysis','extra:dailyAnalysis','anMath','tyt']:
            start(page, key); advance(page, 2); page.locator('#studyTimerStop').click()
            assert page.evaluate('state.studyTimer.sessions.at(-1).taskKey') == key
            assert page.evaluate('state.studyTimer.sessions.at(-1).seconds') == 2
        assert page.evaluate('studyDaySeconds(today())') == 96
        assert non_timer(page) == state_before and gameplay(page) == mechanics
        assert page.evaluate('state.studyTimer.sessions.slice(0,3)') == fixture['studyTimer']['sessions']
        no_overflow(page)
        print('PASS: timed TYT/AYT/branch/general/analysis sessions store the chosen existing ID and date; old assigned/unassigned records intact, no automatic completion or XP.')

        # A plan's duplicate/swapped slots stay selectable; labels retain the actual subject.
        planned = copy.deepcopy(fixture)
        planned['weekPlans'][WEEK][DAY] = ['mathStudy','bio','bio~2']
        planned['swaps'] = {DAY: {'outKey':'mathStudy','inKey':'bio'}}
        plan = context(browser, planned); before = non_timer(plan)
        for key in ['mathStudy','bio~2','extra:bio']:
            start(plan, key); advance(plan, 3); plan.locator('#studyTimerStop').click()
        assert plan.evaluate('studySubjectSummary(today()).find(x=>x.label==="TYT Biyoloji").daySeconds') == 9
        plan.evaluate('state.swaps={};render()')
        assert plan.evaluate('studySubjectSummary(today()).find(x=>x.label==="TYT Biyoloji").daySeconds') == 9
        assert plan.evaluate('state.checks') == before['checks']
        assert plan.evaluate('state.weekPlans') == before['weekPlans']
        print('PASS: existing main, duplicate and swapped slots coexist with all-course selection; time reflects actual saved subject even after a Swap changes.')

        # Manual backdated duration uses the same catalog/session infrastructure; future/live locks stay.
        choose(page, '2026-11-16')
        expect(page.locator('#studyTimerStart')).to_be_disabled()
        page.locator('#addStudySession').click(); page.locator('#studySessionTask').select_option('aytBio')
        page.locator('#studySessionMinutes').fill('4'); page.locator('#studySessionSeconds').fill('30')
        page.locator('#studySessionForm button[type="submit"]').click()
        assert page.evaluate('studyTaskSeconds("2026-11-16","aytBio")') == 270
        assert page.evaluate('state.studyTimer.sessions.at(-1).day') == '2026-11-16'
        choose(page, '2026-11-18'); expect(page.locator('#studyTimerStart')).to_be_disabled(); expect(page.locator('#addStudySession')).to_be_disabled()
        choose(page, DAY)
        assert non_timer(page) == state_before and gameplay(page) == mechanics
        page.locator('[data-tab="backupTab"]').click()
        with page.expect_download() as download: page.locator('#export').click()
        backup = json.loads(Path(download.value.path()).read_text()); saved = page.evaluate('state')
        assert backup['state'] == saved
        page.locator('#import').set_input_files({'name':'timer-catalog.json','mimeType':'application/json','buffer':json.dumps(backup).encode()})
        assert page.evaluate('state') == saved
        page.reload(wait_until='networkidle'); assert page.evaluate('state') == saved
        print('PASS: shared manual editor includes all courses; backdated entries and future locks, JSON round-trip and localStorage reload preserve all records.')

        owner = context(browser, owner=True)
        start(owner, 'aytChem'); advance(owner, 6); owner.locator('#studyTimerStop').click(); advance(owner, 1)
        expect(owner.locator('#cloudStatus')).to_have_text('Kaydedildi')
        assert cloud['studyTimer']['sessions'][-1]['taskKey'] == 'aytChem'
        second = context(browser, owner=True)
        assert second.evaluate('studyTaskSeconds(today(),"aytChem")') == 6
        coach = context(browser, coach=True); advance(coach, 1)
        expect(coach.locator('#studyTimerStart')).to_be_disabled()
        expect(coach.locator('#addStudySession')).to_be_disabled()
        coach.locator('#studySubjectSummary summary').click()
        expect(coach.locator('#studySubjectTimes')).to_contain_text('AYT Kimya')
        before = coach.evaluate('state')
        coach.evaluate('openStudyTimerTaskPicker();startStudyTimerForTask("aytMath","AYT Matematik");openStudySessionEditor();stopStudyTimer()')
        assert coach.evaluate('state') == before
        assert not coach.locator('#studyTimerTaskModal').is_visible()
        assert 'save_yks_rpg_state' in calls and 'get_yks_rpg_coach_state' in calls
        for item in [page,plan,owner,second,coach]: no_overflow(item)
        assert not errors, errors
        print('PASS: existing RPC state sync/second device/coach readonly; full selector and subject summary fit 360px; no JavaScript errors, new storage key or database change.')
        browser.close()
finally:
    for ctx in contexts:
        try: ctx.close()
        except Exception: pass
    server.shutdown()

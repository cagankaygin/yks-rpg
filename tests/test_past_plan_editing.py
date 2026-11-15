"""Backdated edits reuse weekPlans/checks/sessions; browser tests mock existing cloud RPCs."""
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
KEY, TOKEN = 'yks-xp-final-v1', 'synthetic-history-owner-test-only-123456789'
NOW = datetime(2026, 11, 15, 6, tzinfo=timezone.utc)
DAY, WEEK, TODAY = '2026-11-12', '2026-11-09', '2026-11-15'
fixture = {
    'checks': {'2026-10-05|tyt': True, '2026-10-16|paragraph': True},
    'rests': {}, 'purchases': 1, 'refunds': 0, 'spentRests': 0,
    'rewardBuys': [{'type': 'burger', 'date': '2026-10-20T12:00:00Z', 'price': 800, 'couponUsed': False}],
    'weekPlans': {WEEK: {}}, 'swaps': {},
    'planNotes': {DAY: {'physics': 'Elektrikten üç test'}},
    'checkins': {DAY: {'load': 3, 'satisfaction': 4, 'note': 'Eski check-in'}},
    'chestClaims': {WEEK: {'tier': 'Gold', 'reward': 200, 'date': '2026-11-14T06:00:00Z'}},
    'claimedAchievements': {'synthetic-old-claim': True}, 'settings': {'examDate': '2027-06-19'},
    'studyTimer': {'running': None, 'sessions': [
        {'id': 'past-physics', 'day': DAY, 'startedAt': DAY+'T06:00:00Z', 'endedAt': DAY+'T06:30:00Z', 'seconds': 1800, 'label': 'Fizik', 'taskKey': 'physics'},
        {'id': 'past-extra', 'day': DAY, 'startedAt': DAY+'T07:00:00Z', 'endedAt': DAY+'T07:10:00Z', 'seconds': 600, 'label': 'Ek Biyoloji', 'taskKey': 'extra:bio'},
        {'id': 'today-time', 'day': TODAY, 'startedAt': TODAY+'T05:00:00Z', 'endedAt': TODAY+'T05:15:00Z', 'seconds': 900, 'label': 'Kimya', 'taskKey': 'chem'},
    ]},
}
for n in range(7):
    day = (NOW.date()-timedelta(days=6-n)).isoformat()
    fixture['weekPlans'][WEEK][day] = ['geo'] if day != TODAY else ['chem']
    if day != TODAY: fixture['checks'][day+'|geo'] = True
fixture['weekPlans'][WEEK][DAY] = ['geo', 'physics']
fixture['checks'][DAY+'|physics'] = True
fixture['checks'][DAY+'|extra:bio'] = True
# The previous week is perfect, to test derived perfect-week bonuses as well.
fixture['weekPlans']['2026-11-02'] = {}
for n in range(7):
    day = (datetime(2026, 11, 2).date()+timedelta(days=n)).isoformat()
    fixture['weekPlans']['2026-11-02'][day] = ['geo']
    fixture['checks'][day+'|geo'] = True

class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_): pass
server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=str(root)))
threading.Thread(target=server.serve_forever, daemon=True).start()
url = f'http://127.0.0.1:{server.server_port}/'
cloud, calls, contexts, errors, dialogs = copy.deepcopy(fixture), [], [], [], []
accept = True

def rpc(route):
    global cloud
    name, body = route.request.url.rsplit('/', 1)[-1], route.request.post_data_json
    calls.append(name)
    if name == 'get_yks_rpg_owner_state' and body['raw_owner_token'] == TOKEN:
        value = [{'state': cloud, 'updated_at': '2026-11-15T06:00:00Z'}]
    elif name == 'save_yks_rpg_state' and body['raw_owner_token'] == TOKEN:
        cloud = copy.deepcopy(body['new_state']); value = '2026-11-15T06:00:00Z'
    elif name == 'get_yks_rpg_coach_state':
        value = [{'state': cloud, 'updated_at': '2026-11-15T06:00:00Z'}]
    else: raise AssertionError('Unexpected RPC: '+name)
    route.fulfill(json=copy.deepcopy(value))

def context(browser, initial=None, owner=False, coach=False):
    ctx = browser.new_context(viewport={'width': 360, 'height': 900}, timezone_id='Europe/Istanbul', accept_downloads=True, reduced_motion='reduce')
    contexts.append(ctx)
    ctx.route(cdn, lambda r: r.fulfill(body=library, content_type='application/javascript'))
    ctx.route('**/rest/v1/rpc/*', rpc)
    if initial is not None: ctx.add_init_script(f"if(!localStorage.getItem('{KEY}'))localStorage.setItem('{KEY}',{json.dumps(json.dumps(initial))})")
    if owner: ctx.add_init_script(f"localStorage.setItem('yks-rpg-owner-token-v1',{json.dumps(TOKEN)})")
    page = ctx.new_page(); page.on('pageerror', lambda e: errors.append(str(e)))
    def dialog(d):
        dialogs.append(d.message)
        d.accept() if accept else d.dismiss()
    page.on('dialog', dialog)
    page.clock.install(time=NOW); page.clock.pause_at(NOW+timedelta(seconds=1))
    page.goto(url+('#coach=synthetic-history-coach' if coach else ''), wait_until='networkidle')
    return page

def choose(page, day=DAY):
    page.locator('[data-tab="daily"]').click()
    page.locator('#date').fill(day); page.locator('#date').dispatch_event('change')

def plan_card(page, day=DAY): return page.locator(f'.planCard[data-date="{day}"]')
def open_plan(page, day=DAY):
    choose(page, day); page.locator('#editSelectedPlan').click()
    return plan_card(page, day)
def snapshot(page): return page.evaluate('state')
def no_overflow(page): assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')

try:
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=shutil.which('chromium') or shutil.which('chromium-browser'), headless=True, args=['--no-sandbox'])
        page = context(browser, fixture)
        initial = snapshot(page)
        for key, value in fixture.items():
            if key != 'settings': assert initial[key] == value, key
        assert page.evaluate('KEY') == KEY
        baseline = page.evaluate('({totals:totals(),core:weekCore("2026-11-09"),streak:currentAndBestStreak()})')
        assert baseline['streak']['current'] == 13
        card = open_plan(page)
        expect(card.get_by_role('button', name='Ders ekle', exact=True)).to_be_enabled()
        card.locator('.planAdd select').select_option('bio')
        card.locator('.planAdd textarea').fill('Hücrelerden iki test')
        card.get_by_role('button', name='Ders ekle', exact=True).click()
        assert page.evaluate('plannedTasks("2026-11-12")') == ['geo', 'physics', 'bio']
        assert page.evaluate('dayRank("2026-11-12")') == 'B'
        assert round(page.evaluate('completionPct("2026-11-12")'), 3) == round(240/330*100, 3)
        assert page.evaluate('state.weekPlans["2026-11-09"][today()]') == ['chem']
        choose(page)
        expect(page.locator('#tasks')).to_contain_text('Hücrelerden iki test')
        page.locator('#tasks .task').filter(has=page.get_by_text('TYT Biyoloji', exact=True)).locator('input').click()
        assert page.evaluate('dayRank("2026-11-12")') == 'S'
        assert page.evaluate('totals().base') == baseline['totals']['base'] + 90
        # Existing check-in avoids the completion popup; two Bio rows remain distinct.
        assert page.locator('#tasks .task input:checked').count() == 3
        assert page.locator('#completedExtraTasks input[data-extra="bio"]:checked').count() == 1
        page.locator('#completedExtraTasks input[data-extra="bio"]').click()
        assert page.evaluate('dayRank("2026-11-12")') == 'S'
        assert page.evaluate('totals().base') == baseline['totals']['base']
        page.locator('#extraPanel').evaluate('(el)=>el.open=true')
        page.locator('#extraTasks input[data-extra="bio"]').click()
        note = page.locator('.extraStudy[data-study-extra="bio"] .planNoteEditor')
        note.locator('summary').click(); note.locator('textarea').fill('Ek tekrar notu')
        note.get_by_role('button', name='Notu kaydet', exact=True).click()
        assert page.evaluate('state.planNotes["2026-11-12"]["extra:bio"]') == 'Ek tekrar notu'
        print('PASS: calendar → existing planner, past add and notes, weighted Rank, independent main/Extra completion and XP, today unchanged.')

        sessions = page.evaluate('state.studyTimer.sessions')
        card = open_plan(page)
        accept = False
        card.get_by_role('button', name='Fizik Kaldır', exact=False).click()
        assert page.evaluate('plannedTasks("2026-11-12")') == ['geo', 'physics', 'bio']
        accept = True
        card.get_by_role('button', name='Fizik Kaldır', exact=False).click()
        assert page.evaluate('plannedTasks("2026-11-12")') == ['geo', 'bio']
        assert not page.evaluate('state.checks["2026-11-12|physics"] || state.planNotes["2026-11-12"].physics')
        assert page.evaluate('state.studyTimer.sessions') == sessions
        assert page.evaluate('state.chestClaims') == fixture['chestClaims']
        assert page.evaluate('state.claimedAchievements') == fixture['claimedAchievements']
        assert page.evaluate('state.checks["2026-10-16|paragraph"]')
        assert 'kronometre' in dialogs[-1]
        no_overflow(page)
        print('PASS: cancelled/confirmed deletion, removed checks/notes only on selected day; archived timers, former mandatory checks, chest and reward ledgers preserved.')

        choose(page)
        page.locator('.studyTimerSessions summary').click()
        archived = page.locator('[data-session-id="past-physics"]')
        archived.get_by_role('button', name='Düzenle').click()
        expect(page.locator('#studySessionTask')).to_have_value('physics')
        page.locator('#studySessionMinutes').fill('45'); page.locator('#studySessionSeconds').fill('15')
        no_overflow(page)
        page.locator('#studySessionForm button[type="submit"]').click()
        changed = page.evaluate('studySessions(selected).find(x=>x.id==="past-physics")')
        assert changed == {**sessions[0], 'seconds': 2715}
        assert page.evaluate('studyDaySeconds(selected)') == 3315
        expect(page.locator('#weeklyStudyTotal')).to_have_text('1 sa 10 dk')
        xp = page.evaluate('totals().earned')
        page.locator('#addStudySession').click(); page.locator('#studySessionTask').select_option('extra:problem')
        page.locator('#studySessionMinutes').fill('20'); page.locator('#studySessionSeconds').fill('5')
        page.locator('#studySessionForm button[type="submit"]').click()
        assert page.evaluate('studyTaskSeconds(selected,"extra:problem")') == 1205
        assert page.evaluate('totals().earned') == xp
        assert not page.evaluate('isDone(selected,"extra:problem")')
        expect(page.locator('#studyTimerStart')).to_be_disabled()
        assert page.evaluate('state.studyTimer.sessions.find(x=>x.id==="today-time")') == sessions[2]
        saved = snapshot(page)
        page.reload(wait_until='networkidle'); choose(page)
        assert snapshot(page) == saved
        print('PASS: archived timer duration edits keep IDs/timestamps; manual Extra time, correct daily/weekly totals, no XP or live-timer side effects, reload persistence.')

        # Backdated completion affects streak/rank/bonuses, never repeats a chest claim.
        rewards = context(browser, fixture); choose(rewards)
        original = rewards.evaluate('({earned:totals().earned,week:weekCore("2026-11-09"),streak:currentAndBestStreak(),boss:boss(),quests:weekQuestStatus("2026-11-09")})')
        rewards.locator('#tasks .task').filter(has=rewards.get_by_text('TYT Fizik', exact=True)).locator('input').click()
        assert rewards.evaluate('dayRank(selected)') == 'C'
        assert rewards.evaluate('currentAndBestStreak().current') == 2
        assert rewards.evaluate('totals().earned') == original['earned'] - 115  # Physics -115, S -50, newly eligible Comeback +50.
        assert rewards.evaluate('weekCore("2026-11-09").p') == original['week']['p'] - 115
        assert rewards.evaluate('boss().raw') == original['boss']['raw'] - 3
        rewards.evaluate('claimChest();claimChest()')
        assert rewards.evaluate('state.chestClaims') == fixture['chestClaims']
        rewards.locator('#tasks .task').filter(has=rewards.get_by_text('TYT Fizik', exact=True)).locator('input').click()
        assert rewards.evaluate('totals().earned') == original['earned']
        assert rewards.evaluate('currentAndBestStreak()') == original['streak']
        for _ in range(3): rewards.evaluate('claimChest();render()')
        assert rewards.evaluate('totals().earned') == original['earned']
        # Completed perfect-week bonus retracts/reappears once, computed from the existing records.
        choose(rewards, '2026-11-05'); before = rewards.evaluate('totals()')
        rewards.locator('#tasks input').click()
        assert rewards.evaluate('perfectWeekCount()') == before['pw']-1
        assert rewards.evaluate('totals().earned') == before['earned']-125-50-250
        rewards.locator('#tasks input').click()
        assert rewards.evaluate('totals()') == before
        print('PASS: past uncheck/recheck recalculates weekly Rank/XP, streak (13→2→13), Boss and perfect-week bonus; repeated chest claims pay nothing.')

        # Reordering/removing a swapped slot must handle its actual check key only.
        swapped = copy.deepcopy(fixture)
        swapped['weekPlans'][WEEK][DAY] = ['mathStudy', 'geo']
        swapped['swaps'][DAY] = {'outKey': 'mathStudy', 'inKey': 'bio'}
        swapped['checks'][DAY+'|swap:mathStudy:bio'] = True
        swap_page = context(browser, swapped); card = open_plan(swap_page)
        card.get_by_role('button', name='TYT Matematik ↓', exact=True).click()
        assert swap_page.evaluate('isDone("2026-11-12","mathStudy")')
        card.get_by_role('button', name='TYT Matematik Kaldır', exact=True).click()
        assert not swap_page.evaluate('state.swaps["2026-11-12"] || state.checks["2026-11-12|swap:mathStudy:bio"]')
        assert swap_page.evaluate('state.studyTimer.sessions') == fixture['studyTimer']['sessions']
        # Legacy defaults and count-based Rank stay identical until explicit editing.
        legacy = context(browser, fixture); choose(legacy, '2026-10-05')
        assert legacy.evaluate('plannedTasks(selected)') == ['tyt', 'geo', 'physics', 'chem', 'bio']
        assert legacy.evaluate('completionPct(selected)') == 20
        card = open_plan(legacy, '2026-10-05')
        card.locator('.planAdd select').select_option('problem'); card.get_by_role('button', name='Ders ekle', exact=True).click()
        assert legacy.evaluate('plannedTasks("2026-10-05")') == ['tyt', 'geo', 'physics', 'chem', 'bio', 'problem']
        assert legacy.evaluate('state.checks["2026-10-05|tyt"]')
        assert round(legacy.evaluate('completionPct("2026-10-05")'), 6) == round(100/6, 6)
        legacy.reload(wait_until='networkidle')
        assert legacy.evaluate('plannedTasks("2026-10-05").at(-1)') == 'problem'
        print('PASS: swapped slot reorder/delete uses existing session key; legacy task IDs and count-based Rank persist through edits/reload.')

        # Clear operations are explicit, retain all timer records, and never disturb a live clock.
        safety = context(browser, fixture)
        safety.evaluate('startStudyTimerForTask("chem","Kimya")')
        running = safety.evaluate('studyRunning()')
        card = open_plan(safety)
        before_clear = snapshot(safety)
        accept = False; card.get_by_role('button', name='Günün planını temizle', exact=True).click()
        assert snapshot(safety) == before_clear
        accept = True; card.get_by_role('button', name='Günün planını temizle', exact=True).click()
        assert safety.evaluate('plannedTasks("2026-11-12")') == []
        assert safety.evaluate('studyRunning()') == running
        assert safety.evaluate('state.studyTimer.sessions') == fixture['studyTimer']['sessions']
        assert safety.evaluate('state.weekPlans["2026-11-09"][today()]') == ['chem']
        assert safety.evaluate('isDone("2026-11-12","extra:bio")')
        safety.locator('#planWeek').fill('2026-11-02'); safety.locator('#planWeek').dispatch_event('change')
        before_week = snapshot(safety)
        accept = False; safety.locator('#resetPlanWeek').click()
        assert snapshot(safety) == before_week
        accept = True; safety.locator('#resetPlanWeek').click()
        assert safety.evaluate('datesBetween("2026-11-02","2026-11-08").every(s=>plannedTasks(s).length===0)')
        assert safety.evaluate('studyRunning()') == running
        assert safety.evaluate('state.chestClaims') == fixture['chestClaims']
        assert safety.evaluate('state.studyTimer.sessions') == fixture['studyTimer']['sessions']
        print('PASS: day/week clear confirmations, explicit empty legacy plans, selected week only; saved sessions, today plan, live timer and paid rewards remain intact.')

        # Export/import carries the existing schema plus optional manual markers and Extra notes.
        page.locator('[data-tab="backupTab"]').click()
        with page.expect_download() as download: page.locator('#export').click()
        exported = json.loads(Path(download.value.path()).read_text())
        assert exported['state'] == saved
        page.locator('#import').set_input_files({'name': 'history.json', 'mimeType': 'application/json', 'buffer': json.dumps(exported).encode()})
        assert snapshot(page) == saved
        old = context(browser, {'checks': {'2026-10-05|tyt': True}, 'rests': {}})
        assert old.evaluate('isDone("2026-10-05","tyt")')
        assert old.evaluate('state.studyTimer.sessions') == []
        print('PASS: JSON export/import round-trip, old state defaults and legacy checks.')

        # Cloud is the existing state JSON over the same RPCs. Coach views all, writes nothing.
        owner = context(browser, owner=True); choose(owner)
        owner.locator('#addStudySession').click(); owner.locator('#studySessionTask').select_option('extra:paragraph')
        owner.locator('#studySessionMinutes').fill('12'); owner.locator('#studySessionSeconds').fill('0')
        owner.locator('#studySessionForm button[type="submit"]').click(); owner.clock.run_for(1500)
        expect(owner.locator('#cloudStatus')).to_have_text('Kaydedildi')
        assert 'save_yks_rpg_state' in calls
        assert cloud['studyTimer']['sessions'][-1]['taskKey'] == 'extra:paragraph'
        coach = context(browser, coach=True); choose(coach); coach.clock.run_for(1)
        expect(coach.locator('#addStudySession')).to_be_disabled()
        expect(coach.locator('#tasks input').first).to_be_disabled()
        card = open_plan(coach); coach.clock.run_for(1)
        expect(card.get_by_role('button', name='Ders ekle', exact=True)).to_be_disabled()
        coach_before = snapshot(coach)
        coach.evaluate('setDayPlan("2026-11-12",[]);writeDayPlan("2026-11-12",[]);removePlannedLesson("2026-11-12","physics");resetDayPlan("2026-11-12");resetWeekPlan();openStudySessionEditor();saveStudySessionEdit();deleteStudySession("past-extra");savePlanNote("2026-11-12","physics","bad");claimChest()')
        assert snapshot(coach) == coach_before
        assert coach.evaluate('studyTaskSeconds("2026-11-12","extra:paragraph")') == 720
        for item in (page,rewards,swap_page,legacy,owner,coach): no_overflow(item)
        assert not errors, errors
        print('PASS: existing owner/coach RPC state sync; readonly UI and guarded mutations; 360px no overflow, no JavaScript errors.')
        browser.close()
finally:
    for ctx in contexts:
        try: ctx.close()
        except Exception: pass
    server.shutdown()

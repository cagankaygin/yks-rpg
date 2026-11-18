"""Home-only television checklist reward with the existing daily ledger. No real student/cloud data is used."""
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
fixture['weekPlans'][WEEK][DAY]=['bio','geo','physics','chem','mathStudy','tr']
fixture['checkins'][DAY]={'load':3,'satisfaction':4,'note':'Bugünkü kayıt'}
fixture['questionVault']={'books':[{'id':'book','name':'Eski geometri','subject':'geo','createdAt':'2026-09-28'}],'questions':[]}
for id,active,due,mastered in [('old-ready',False,'',False),('old-due',True,DAY,False),('old-mastered',True,'',True)]:
 fixture['questionVault']['questions'].append({'id':id,'sourceType':'book','bookId':'book','topic':'Üçgenler','page':'12','questionNo':id,'addedAt':'2026-09-28','firstEligibleAt':'2026-10-05','active':active,'successStage':3 if mastered else 1 if active else 0,'lastResult':'solved' if active else None,'lastAttemptAt':'2026-11-03' if active else '', 'nextDueAt':due,'mastered':mastered,'history':[{'date':'2026-11-03','result':'solved'}] if active else []})
cloud, calls, contexts, errors = copy.deepcopy(fixture), [], [], []
accept_dialog=True

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
    page = ctx.new_page(); page.on('pageerror', lambda e: errors.append(str(e))); page.on('dialog', lambda d: d.accept() if accept_dialog else d.dismiss())
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


def lock_tab(page): page.locator('[data-tab="lockInTab"]').click()
def open_evaluation(page): page.locator('#lockInStop').click()
def select_rules(page, keys=('phone','period','breaks','social')):
    for key in keys: page.locator(f'[data-lock-rule="{key}"]').check()
def submit(page): page.locator('#lockInEvaluationForm button[type="submit"]').click()
def reward(page): return page.evaluate('lockInDayLedger(today()).reward')
def penalty(page): return page.evaluate('lockInDayLedger(today()).penalty')

try:
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=shutil.which('chromium') or shutil.which('chromium-browser'),headless=True,args=['--no-sandbox'])
        page=context(browser,fixture); lock_tab(page)
        initial=page.evaluate('state'); before=gameplay(page)
        # Other environments retain exactly their four common rules and 55 XP ceiling.
        for env in ['university','bilim']:
            page.locator(f'[data-lockin-env="{env}"]').click();page.locator('#lockInStart').click();open_evaluation(page)
            assert page.locator('[data-lock-rule]').count()==4
            assert page.locator('[data-lock-rule="tv"]').count()==0
            select_rules(page);expect(page.locator('#lockInEvaluationTotals')).to_contain_text('Kazanılacak: +55 XP')
            page.locator('#cancelLockInEvaluation').click();page.locator('#lockInStop').click();submit(page)
        assert reward(page)==0
        page.locator('[data-lockin-env="home"]').click();page.locator('#lockInStart').click();open_evaluation(page)
        assert page.locator('[data-lock-rule]').count()==5
        expect(page.locator('#lockInChecklist')).to_contain_text('Günlük ders programım tamamlanmadan televizyon izlemedim. +10 XP')
        select_rules(page,('tv',));expect(page.locator('#lockInEvaluationTotals')).to_contain_text('Kazanılacak: +10 XP');submit(page)
        assert reward(page)==10
        assert page.evaluate('totals().earned')==before['xp']['earned']+10
        assert page.evaluate('lockInDay().evaluations.at(-1).awarded')==['tv']
        for key in ['checks','weekPlans','questionVault','studyTimer','rewardBuys']:
            assert page.evaluate(f'state.{key}')==initial[key]
        page.reload(wait_until='networkidle');lock_tab(page)
        page.locator('#lockInStart').click();open_evaluation(page);select_rules(page,('tv',))
        expect(page.locator('#lockInEvaluationTotals')).to_contain_text('Kazanılacak: +0 XP');submit(page)
        assert reward(page)==10
        page.locator('[data-lockin-env="bilim"]').click();page.locator('#lockInStart').click();open_evaluation(page);select_rules(page)
        assert page.locator('[data-lock-rule="tv"]').count()==0
        submit(page);assert reward(page)==65
        expect(page.locator('#lockInState')).to_contain_text('65/65 XP')
        page.locator('[data-lockin-env="home"]').click();page.locator('#lockInStart').click();open_evaluation(page);select_rules(page,('phone','period','breaks','social','tv'))
        expect(page.locator('#lockInEvaluationTotals')).to_contain_text('Kazanılacak: +0 XP');submit(page)
        assert reward(page)==65
        expect(page.locator('#lockInHistory')).to_contain_text('Günlük ders programım tamamlanmadan televizyon izlemedim.')
        assert page.evaluate('state.lockIn')==page.evaluate('normalizeLockIn(state.lockIn)')
        print('PASS: TV is home-only, pays 10 XP, stays once-only across reload/mode changes, shares original common-rule guards; daily total 65, other modes still offer 55, unrelated data intact.')

        # All home rules + a confirmed social penalty: no social +20, TV still pays +10.
        punished=context(browser,fixture);lock_tab(punished);punished.locator('[data-lockin-env="home"]').click();punished.locator('#lockInStart').click();open_evaluation(punished)
        select_rules(punished,('phone','period','breaks','social','tv'));punished.locator('#lockInPenalty').check()
        expect(punished.locator('[data-lock-rule="social"]')).not_to_be_checked()
        expect(punished.locator('#lockInEvaluationTotals')).to_contain_text('Kazanılacak: +45 XP')
        expect(punished.locator('#lockInEvaluationTotals')).to_contain_text('Net: -1455 XP')
        accept_dialog=False;submit(punished);assert penalty(punished)==0 and reward(punished)==0
        accept_dialog=True;submit(punished);assert penalty(punished)==1500 and reward(punished)==45
        punished.evaluate('submitLockInEvaluation()');assert penalty(punished)==1500
        # Out-of-scope imported or forged rewards never count in either non-home mode.
        for env in ['bilim','university']:
            forged=copy.deepcopy(fixture)
            forged['lockIn']={'days':{DAY:{'env':env,'active':False,'startedAt':'','evaluations':[{'id':'foreign-tv','env':env,'at':DAY+'T06:00:00Z','checks':{'tv':True},'awarded':['tv'],'penalty':False}]}}}
            invalid=context(browser,forged);assert reward(invalid)==0
            invalid.evaluate('lockInDay().evaluations[0].awarded=["tv"]');assert reward(invalid)==0
        print('PASS: existing 1500 penalty still requires confirmation, social exclusion holds, home TV may combine with other eligible rules, duplicate penalty and out-of-mode imported TV claims are blocked.')

        # New field survives existing transport; old records do not gain phantom TV XP.
        saved=page.evaluate('state');page.locator('[data-tab="backupTab"]').click()
        with page.expect_download() as download:page.locator('#export').click()
        backup=json.loads(Path(download.value.path()).read_text());assert backup['state']==saved
        page.locator('#import').set_input_files({'name':'home-tv.json','mimeType':'application/json','buffer':json.dumps(backup).encode()})
        assert page.evaluate('state')==saved
        cloud=copy.deepcopy(saved)
        owner=context(browser,owner=True);lock_tab(owner);owner.locator('#lockInStart').click();open_evaluation(owner);select_rules(owner,('tv',));submit(owner);advance(owner,1)
        expect(owner.locator('#cloudStatus')).to_have_text('Kaydedildi');assert cloud['lockIn']['days'][DAY]['evaluations'][-1]['checks']['tv']
        coach=context(browser,coach=True);advance(coach,1);lock_tab(coach);before_coach=coach.evaluate('state')
        expect(coach.locator('#lockInStop')).to_be_disabled()
        coach.evaluate('startLockIn();stopLockIn();submitLockInEvaluation()');assert coach.evaluate('state')==before_coach
        assert coach.evaluate('lockInDayLedger(today()).reward')==65
        for item in [page,punished,owner,coach]:no_overflow(item)
        assert not errors,errors
        print('PASS: JSON/localStorage and mocked owner/coach sync retain TV claims; old data compatibility, coach readonly, 360px and syntax/runtime smoke checks.')
        browser.close()
finally:
    for ctx in contexts:
        try:ctx.close()
        except Exception:pass
    server.shutdown()

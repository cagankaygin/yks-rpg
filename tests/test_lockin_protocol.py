"""Lock-In periods/XP, separate breaks and question difficulty. No real student/cloud data is used."""
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
        page=context(browser,fixture)
        expect(page).to_have_title('YKS RPG V3.34')
        assert page.locator('#daily #lockInPanel').count()==0
        assert page.locator('#lockInTab #lockInPanel').count()==1
        initial_questions=page.evaluate('state.questionVault.questions')
        assert all('difficulty' not in q for q in initial_questions)
        assert page.evaluate('state.studyTimer.sessions')==fixture['studyTimer']['sessions']
        lock_tab(page); rules=None; baseline=gameplay(page)
        for env in ['bilim','university','home']:
            page.locator(f'[data-lockin-env="{env}"]').click()
            current=page.locator('#lockInRules').inner_text()
            if rules is not None: assert rules==current
            rules=current
        assert gameplay(page)==baseline
        plan_before=page.evaluate('state.weekPlans')
        for _ in range(3): page.locator('#addLockPeriod').click()
        page.locator('#addLockPeriod').click(); extra_period=page.evaluate('lockInDay().periods.at(-1).id')
        accept_dialog=False; page.locator(f'[data-period-id="{extra_period}"]').get_by_role('button',name='Periyodu kaldır').click()
        assert page.evaluate('lockInDay().periods.length')==4
        accept_dialog=True; page.locator(f'[data-period-id="{extra_period}"]').get_by_role('button',name='Periyodu kaldır').click()
        assert page.evaluate('lockInDay().periods.length')==3
        ids=page.evaluate('lockInDay().periods.map(p=>p.id)')
        for i,key in enumerate(['bio','geo','physics','chem','mathStudy','tr']): page.locator(f'[data-period-slot="{key}"]').select_option(ids[i//2])
        page.locator('#lockMealAfter').select_option(ids[1])
        assert page.evaluate('lockInDay().periods.map(p=>p.slots.length)')==[2,2,2]
        assert page.evaluate('state.weekPlans')==plan_before
        expect(page.locator(f'[data-period-id="{ids[1]}"]')).to_contain_text('Yemek molası · 60 dk')
        # Arbitrary 1-2-3 arrangement: no fixed group size or plan mutation.
        page.locator('[data-period-slot="geo"]').select_option(ids[2])
        assert page.evaluate('lockInDay().periods.map(p=>p.slots.length)')==[1,2,3]
        page.locator('[data-period-slot="geo"]').select_option(ids[0])
        page.locator('#lockInStart').click()
        session_id=page.evaluate('lockInDay().sessionId')
        page.locator('[data-lockin-env="bilim"]').click()
        assert page.evaluate('lockInDay().sessionId')==session_id
        page.locator('#lockDailyLink').click()
        expect(page.locator('#lockInIndicator')).to_contain_text('Bilim aktif')
        for name in ['TYT Biyoloji','Geometri']:
            page.locator('#tasks .task').filter(has=page.get_by_text(name,exact=True)).locator('input').click()
        lock_tab(page)
        expect(page.locator(f'[data-period-id="{ids[0]}"]')).to_have_class('periodCard done')
        assert page.evaluate('state.weekPlans')==plan_before
        before=page.evaluate('totals()'); before_week=page.evaluate('weekCore(monday(today())).p'); before_day=page.evaluate('earnedByDay()[today()]')
        open_evaluation(page); select_rules(page)
        expect(page.locator('#lockInEvaluationTotals')).to_contain_text('Kazanılacak: +55 XP')
        no_overflow(page); submit(page)
        assert reward(page)==55 and penalty(page)==0
        assert page.evaluate('totals().balance')==before['balance']+55
        assert page.evaluate('lockInDay().active') is False
        page.evaluate('submitLockInEvaluation();submitLockInEvaluation()')
        assert reward(page)==55
        # New mode/new session cannot award any rule twice on the same day.
        page.locator('[data-lockin-env="home"]').click(); page.locator('#lockInStart').click(); open_evaluation(page); select_rules(page)
        expect(page.locator('#lockInEvaluationTotals')).to_contain_text('Kazanılacak: +0 XP'); submit(page)
        assert reward(page)==55
        page.locator('#lockInStart').click(); open_evaluation(page)
        page.locator('[data-lock-rule="social"]').check(); page.locator('#lockInPenalty').check()
        expect(page.locator('[data-lock-rule="social"]')).not_to_be_checked()
        expect(page.locator('#lockInEvaluationTotals')).to_contain_text('Net: -1500 XP')
        accept_dialog=False; submit(page)
        assert penalty(page)==0 and page.evaluate('lockInDay().active')
        accept_dialog=True; submit(page)
        assert penalty(page)==1500 and reward(page)==55
        assert page.evaluate('totals().balance')==before['balance']+55-1500
        assert page.evaluate('weekCore(monday(today())).p')==before_week+55-1500
        assert page.evaluate('earnedByDay()[today()]')==before_day+55-1500
        expect(page.locator('#daynotice')).to_contain_text('Lock-In -1445 XP')
        expect(page.locator('#lockInHistory')).to_contain_text('Arkadaşlarımla takılmak için günlük ders programımı yarıda bıraktım.')
        page.evaluate('submitLockInEvaluation();stopLockIn()')
        assert penalty(page)==1500
        page.reload(wait_until='networkidle'); assert penalty(page)==1500 and reward(page)==55
        print('PASS: separate Lock-In tab/shared rules/indicator; arbitrary 2-2-2 and 1-2-3 periods without changing plan; completion follows daily checks; per-rule daily 55 cap across modes/restarts, confirmation cancellation, single 1500 penalty, history and net daily/weekly XP; reload guards.')

        first_penalty=context(browser,fixture); lock_tab(first_penalty); first_penalty.locator('#lockInStart').click(); open_evaluation(first_penalty); select_rules(first_penalty); first_penalty.locator('#lockInPenalty').check()
        expect(first_penalty.locator('#lockInEvaluationTotals')).to_contain_text('Kazanılacak: +35 XP')
        expect(first_penalty.locator('#lockInEvaluationTotals')).to_contain_text('Net: -1465 XP'); submit(first_penalty)
        assert reward(first_penalty)==35 and penalty(first_penalty)==1500
        assert 'social' not in first_penalty.evaluate('lockInDay().evaluations[0].awarded')
        first_penalty.locator('#lockInStart').click(); open_evaluation(first_penalty); select_rules(first_penalty,('social',)); submit(first_penalty)
        assert reward(first_penalty)==55 and penalty(first_penalty)==1500
        emergency=context(browser,fixture); lock_tab(emergency); emergency.locator('#lockInStart').click(); open_evaluation(emergency)
        expect(emergency.locator('#lockInEvaluation')).to_contain_text('Acil durumlar, sağlık sorunları ve zorunlu program değişiklikleri ceza kapsamında değildir.')
        submit(emergency); assert penalty(emergency)==0 and reward(emergency)==0
        print('PASS: social +20 cannot coexist with penalty in one evaluation; other rules pay 35, later social reward remains once-only; unchecked/urgent exit has no automatic penalty.')

        timer=context(browser,fixture); timer.evaluate('()=>{window.soundCalls=0;window.Audio=function(){soundCalls++};window.AudioContext=function(){soundCalls++}}')
        before_state=non_timer(timer); before_game=gameplay(timer)
        start(timer,'aytPhysics'); advance(timer,20)
        timer.locator('#studyBreakButtons [data-study-break="short"]').click(); advance(timer,305)
        assert timer.evaluate('runningStudySeconds()')==20
        expect(timer.locator('#studyBreakStatus')).to_contain_text('Aşım +00:00:05')
        assert timer.evaluate('soundCalls')==0
        timer.reload(wait_until='networkidle')
        assert timer.evaluate('runningStudySeconds()')==20 and timer.evaluate('studyBreakElapsed()')==305
        timer.locator('#studyBreakEnd').click(); advance(timer,10); timer.locator('#studyTimerStop').click()
        assert timer.evaluate('studyTaskSeconds(today(),"aytPhysics")')==30
        assert timer.evaluate('state.studyTimer.breaks.at(-1).seconds')==305
        assert timer.evaluate('state.studyTimer.breaks.at(-1).overrunSeconds')==5
        # Standalone breaks use the same break store and block a second working timer.
        for kind,seconds,overrun in [('period',1507,7),('meal',3601,1)]:
            timer.locator(f'#studyBreakButtons [data-study-break="{kind}"]').click()
            expect(timer.locator('#studyTimerStart')).to_be_disabled()
            timer.evaluate('startStudyTimerForTask("aytMath","AYT Matematik")'); assert timer.evaluate('studyRunning()') is None
            advance(timer,seconds); expect(timer.locator('#studyBreakStatus')).to_contain_text('Aşım +00:00:0'+str(overrun))
            timer.locator('#studyBreakEnd').click()
            assert timer.evaluate('state.studyTimer.breaks.at(-1).type')==kind
            assert timer.evaluate('state.studyTimer.breaks.at(-1).seconds')==seconds
        assert timer.evaluate('studyBreakSeconds(today())')==5413
        start(timer,'extra:bio'); advance(timer,15); timer.locator('#studyBreakButtons [data-study-break="meal"]').click(); advance(timer,10); timer.locator('#studyTimerStop').click()
        assert timer.evaluate('state.studyTimer.sessions.at(-1).seconds')==15
        assert timer.evaluate('studyBreakRunning()') is None
        assert timer.evaluate('studyBreakSeconds(today())')==5423
        assert non_timer(timer)==before_state and gameplay(timer)==before_game
        assert timer.evaluate('state.studyTimer.sessions.slice(0,3)')==fixture['studyTimer']['sessions']
        # A period's scheduled meal button starts the shared standalone break.
        lock_tab(page); page.locator(f'[data-period-id="{ids[1]}"] [data-study-break="meal"]').click(); advance(page,3)
        assert page.evaluate('studyBreakRunning().type')=='meal'; page.locator('#lockBreakEnd').click()
        print('PASS: 5/25/60 minute breaks, silent overruns, active-break reload, work net time excludes all breaks; standalone/period breaks share one timer; finishing during a break saves both once; no XP/completion/plan mutation.')

        questions=context(browser,fixture); questions.locator('[data-tab="vaultTab"]').click()
        old=questions.evaluate('state.questionVault.questions')
        assert all('difficulty' not in q for q in old)
        # Existing ready question can receive a difficulty without altering its learning record.
        questions.locator('#vaultReadyDetails').evaluate('(el)=>el.open=true')
        ready=questions.locator('#vaultReadyList [data-question-id="old-ready"]')
        ready.locator('.vaultDifficultySelect').select_option('brutal')
        changed=questions.evaluate('state.questionVault.questions.find(q=>q.id==="old-ready")')
        assert changed=={**old[0],'difficulty':'brutal'}
        questions.locator('#vaultFilterDifficulty').select_option('hard')
        assert questions.locator('#vaultReadyList .vaultQuestion').count()==0
        questions.locator('#vaultFilterDifficulty').select_option('brutal')
        expect(questions.locator('#vaultReadyList .vaultDifficultyBadge')).to_have_text('🔴 İnsafsız')
        questions.locator('#vaultFilterDifficulty').select_option('unknown')
        assert questions.locator('#vaultDueList [data-question-id="old-due"]').count()==1
        questions.locator('#vaultDueList .vaultDifficultySelect').select_option('hard')
        assert questions.locator('#vaultDueList .vaultQuestion').count()==0
        questions.locator('#vaultFilterDifficulty').select_option('hard')
        expect(questions.locator('#vaultDueList .vaultDue')).to_have_class('vaultDue today')
        questions.locator('#vaultFilterDifficulty').select_option('')
        questions.locator('#vaultQuestionTopic').fill('Yeni konu'); questions.locator('#vaultPage').fill('20'); questions.locator('#vaultQuestionNo').fill('1'); questions.locator('#vaultDifficulty').select_option('medium'); questions.locator('#vaultQuestionForm button[type="submit"]').click()
        assert questions.evaluate('state.questionVault.questions.at(-1).difficulty')=='medium'
        assert questions.evaluate('state.questionVault.questions.at(-1).firstEligibleAt')=='2026-11-24'
        # Quick and mock-source forms also carry the chosen difficulty.
        questions.locator('#quickVaultFab').click(); questions.locator('#quickVaultTopic').fill('Hızlı konu'); questions.locator('#quickVaultPage').fill('30'); questions.locator('#quickVaultQuestionNo').fill('2'); questions.locator('#quickVaultDifficulty').select_option('hard'); questions.locator('#quickVaultForm button[type="submit"]').click()
        assert questions.evaluate('state.questionVault.questions.at(-1).difficulty')=='hard'
        questions.locator('#closeQuickVault').click()
        questions.evaluate('state.mockExams.push({id:"mock-fixture",date:today(),type:"TYT",name:"Test denemesi",scores:{turkish:{correct:30,wrong:5},social:{correct:10,wrong:5},math:{correct:30,wrong:8},science:{correct:10,wrong:5}}});openMockVault("mock-fixture")')
        questions.locator('#mockVaultSubject').select_option('mathStudy'); questions.locator('#mockVaultQuestionNo').fill('9'); questions.locator('#mockVaultDifficulty').select_option('brutal'); questions.locator('#mockVaultForm button[type="submit"]').click()
        assert questions.evaluate('state.questionVault.questions.at(-1).difficulty')=='brutal'
        questions.locator('#closeMockVault').click()
        questions.evaluate('openMathAnalysis("mock-fixture")')
        questions.locator('#mathAnalysisQuestionNo').fill('10'); questions.locator('input[name="mathAnalysisMethod"][value="video"]').check(); questions.locator('#mathAnalysisDifficulty').select_option('hard'); questions.locator('#mathAnalysisForm button[type="submit"]').click()
        assert questions.evaluate('state.questionVault.questions.at(-1).difficulty')=='hard'
        questions.locator('#closeMathAnalysis').click()
        assert questions.evaluate('state.questionVault.questions.find(q=>q.id==="old-mastered")')==old[2]
        assert questions.evaluate('state.checks')==fixture['checks']
        print('PASS: old questions remain unassigned; editable difficulty/filter on ready/due lists, status colors/dates/stages unchanged; normal/quick/mock/math-analysis adds carry difficulty and original 7-day wait.')

        # JSON round trip includes running breaks, period definitions, evaluations and difficulty.
        combined=page.evaluate('state'); combined['studyTimer']=timer.evaluate('state.studyTimer'); combined['questionVault']=questions.evaluate('state.questionVault')
        # Keep an active standalone break in the backup to verify recovery.
        timer.locator('#studyBreakButtons [data-study-break="short"]').click(); advance(timer,2); combined['studyTimer']=timer.evaluate('state.studyTimer')
        canonical=page.evaluate('(s)=>normalizeRemoteState(s)',combined)
        for field in ['studyTimer','lockIn']: assert canonical[field]==combined[field], field
        for old_question,new_question in zip(combined['questionVault']['questions'],canonical['questionVault']['questions']):
            for key,value in old_question.items(): assert new_question[key]==value,(old_question['id'],key)
        page.evaluate('(s)=>{state=s;save();render()}',canonical)
        page.locator('[data-tab="backupTab"]').click()
        with page.expect_download() as download: page.locator('#export').click()
        backup=json.loads(Path(download.value.path()).read_text()); saved=page.evaluate('state'); assert backup['state']==saved
        page.locator('#import').set_input_files({'name':'v334.json','mimeType':'application/json','buffer':json.dumps(backup).encode()})
        assert page.evaluate('state')==saved
        page.reload(wait_until='networkidle'); assert page.evaluate('state')==saved
        assert page.evaluate('studyBreakRunning().type')=='short'
        # Duplicate imported evaluation IDs cannot duplicate a penalty or rule reward.
        duplicated=copy.deepcopy(saved); duplicated['lockIn']['days'][DAY]['evaluations']*=2
        dup=context(browser,duplicated); assert penalty(dup)==1500 and reward(dup)==55
        cloud=copy.deepcopy(saved)
        owner=context(browser,owner=True); owner.evaluate('endStudyBreak()'); advance(owner,1)
        expect(owner.locator('#cloudStatus')).to_have_text('Kaydedildi')
        coach=context(browser,coach=True); advance(coach,1); coach.locator('#lockInIndicator').click()
        expect(coach.locator('#lockInStart')).to_be_disabled(); expect(coach.locator('#addLockPeriod')).to_be_disabled()
        before=coach.evaluate('state')
        coach.evaluate('startLockIn();stopLockIn();submitLockInEvaluation();setLockInEnv("bilim");addLockPeriod();assignLockPeriod("bio","");setLockMeal("");startStudyBreak("short");finishStudyBreak();endStudyBreak();setVaultDifficulty("old-ready","medium")')
        assert coach.evaluate('state')==before
        coach.locator('[data-tab="vaultTab"]').click(); coach.locator('#vaultFilterDifficulty').select_option('brutal')
        assert coach.locator('.vaultDifficultySelect').count()==0
        assert coach.evaluate('state.questionVault.questions.find(q=>q.id==="old-ready").difficulty')=='brutal'
        for item in [page,first_penalty,emergency,timer,questions,owner,coach]: no_overflow(item)
        assert not errors,errors
        print('PASS: JSON import/export/reload preserve all new data and active break; duplicate imported evaluations do not multiply XP/penalty; existing owner/coach RPC sync, readonly mutations blocked, 360px no overflow and no JS errors.')
        browser.close()
finally:
    for ctx in contexts:
        try:ctx.close()
        except Exception:pass
    server.shutdown()

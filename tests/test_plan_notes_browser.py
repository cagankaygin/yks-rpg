"""Study-flow and plan-note browser tests. All cloud RPCs use an isolated in-memory state."""
import argparse
import copy
import functools
import http.server
import json
import shutil
import threading
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--supabase-js', type=Path, help='Optional local Supabase browser library')
parser.add_argument('--baseline', type=Path, help='Optional previous index.html for scoring regression checks')
args = parser.parse_args()
repo = Path(__file__).resolve().parents[1]
CDN = 'https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2'
library = args.supabase_js.read_bytes() if args.supabase_js else urllib.request.urlopen(CDN, timeout=30).read()
KEY = 'yks-xp-final-v1'
OWNER = 'test-only-owner-not-real-1234567890123456'
COACH = 'test-only-coach-not-real-1234567890123456'
TODAY, FUTURE = '2026-10-15', '2026-10-19'
legacy = {
    'checks': {'2026-10-05|tyt': True, '2026-10-10|geo': True, '2026-10-14|paragraph': True, '2026-10-14|problem': True},
    'rests': {}, 'purchases': 1, 'checkins': {'2026-10-10': {'load': 3, 'satisfaction': 4, 'note': 'Eski kayıt'}},
    'settings': {'examDate': '2027-06-19', 'morningWakeTime': '06:30', 'studyStartTime': '09:00'},
    'weekPlans': {'2026-10-12': {TODAY: ['mat', 'geo', 'bio']}, FUTURE: {FUTURE: ['hist']}},
    'morningProtocol': {'2026-10-14': {'checks': {'wake': True}, 'timestamps': {'wake': '2026-10-14T03:30:00Z'}}},
}

class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_): pass

class Backend:
    def __init__(self):
        self.state = copy.deepcopy(legacy)
        self.calls, self.unexpected = [], []

    def request(self, route):
        request = route.request
        if request.method == 'OPTIONS':
            return route.fulfill(status=200, headers={'access-control-allow-origin': '*', 'access-control-allow-headers': '*'})
        name, body = request.url.rsplit('/', 1)[-1], request.post_data_json
        self.calls.append((name, copy.deepcopy(body)))
        if name == 'get_yks_rpg_owner_state':
            result = [{'state': self.state, 'updated_at': '2026-10-15T06:00:00Z'}] if body['raw_owner_token'] == OWNER else []
        elif name == 'get_yks_rpg_coach_state':
            result = [{'state': self.state, 'updated_at': '2026-10-15T06:00:00Z'}] if body['raw_token'] == COACH else []
        elif name == 'save_yks_rpg_state' and body['raw_owner_token'] == OWNER:
            self.state = copy.deepcopy(body['new_state'])
            result = '2026-10-15T07:00:00Z'
        else:
            self.unexpected.append(name)
            return route.fulfill(status=403, json={'message': 'Unexpected RPC'})
        route.fulfill(status=200, json=copy.deepcopy(result), headers={'access-control-allow-origin': '*'})

server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(QuietHandler, directory=str(repo)))
threading.Thread(target=server.serve_forever, daemon=True).start()
URL = f'http://127.0.0.1:{server.server_port}/'
errors, contexts = [], []
backend = Backend()

def context(browser, role=None, initial=None):
    ctx = browser.new_context(accept_downloads=True, timezone_id='Europe/Istanbul', viewport={'width': 360, 'height': 900}, reduced_motion='reduce')
    contexts.append(ctx)
    ctx.route(CDN, lambda r: r.fulfill(body=library, content_type='application/javascript'))
    ctx.route('**/rest/v1/rpc/*', backend.request)
    if initial is not None:
        ctx.add_init_script(f"if(!localStorage.getItem('{KEY}'))localStorage.setItem('{KEY}',{json.dumps(json.dumps(initial))})")
    if role == 'owner':
        ctx.add_init_script(f"localStorage.setItem('yks-rpg-owner-token-v1',{json.dumps(OWNER)})")
    page = ctx.new_page()
    page.clock.install(time=datetime(2026, 10, 15, 6, tzinfo=timezone.utc))
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('dialog', lambda dialog: dialog.accept())
    return page

def tab(page, key):
    page.locator(f'[data-tab="{key}"]').click()
    expect(page.locator('#' + key)).to_be_visible()

def select_day(page, day):
    page.locator('#date').fill(day)
    page.locator('#date').dispatch_event('change')

def plan_week(page, week):
    tab(page, 'planTab')
    page.locator('#planWeek').fill(week)
    page.locator('#planWeek').dispatch_event('change')

def card(page, day): return page.locator(f'.planCard[data-date="{day}"]')
def note_editor(page, day, key): return card(page, day).locator(f'.planLessonNote[data-note-slot="{key}"]')

def edit_note(page, day, key, text):
    editor = note_editor(page, day, key)
    if not editor.locator('details').evaluate('(x)=>x.open'):
        editor.locator('summary').click()
    editor.locator('textarea').fill(text)
    editor.get_by_role('button', name='Notu kaydet', exact=True).click()

def add_lesson(page, day, key, text=''):
    row = card(page, day).locator('.planAdd')
    row.locator('select').select_option(key)
    row.locator('textarea').fill(text)
    row.get_by_role('button', name='Ders ekle', exact=True).click()

def no_overflow(page): assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
def metrics(page): return page.evaluate('({totals:totals(),boss:boss(),skill:skillXP(),rank:completionPct(today()),streak:currentAndBestStreak(),morning:morningStatistics(),quest:weekQuestStatus(monday(today()))})')

def test_optional_basics(browser):
    fixture = copy.deepcopy(legacy)
    fixture['weekPlans']['2026-10-12'][TODAY] = ['geo', 'physics']
    fixture['checks'].update({
        '2026-10-14|paragraph': True, '2026-10-14|problem': True,
        '2026-10-14|extra:paragraph': True, TODAY + '|geo': True,
    })
    page = context(browser, initial=fixture)
    page.goto(URL, wait_until='networkidle')
    assert page.evaluate('state.checks') == fixture['checks']
    assert page.evaluate('tasks(today())') == ['geo', 'physics']
    assert page.evaluate("datesBetween(FLOW_START,add(FLOW_START,13)).every(day=>!defaultTasks(day).some(k=>['paragraph','problem'].includes(k))&&!plannedTasks(day).some(k=>['paragraph','problem'].includes(k)))")
    assert page.locator('#tasks .task').count() == 2
    assert 'Paragraf' not in page.locator('#tasks').inner_text()
    assert 'Problem' not in page.locator('#tasks').inner_text()
    assert page.evaluate('rankWeights(today())') == {'done': 120, 'total': 230}
    assert abs(page.evaluate('completionPct(today())') - 120/230*100) < 1e-9
    assert page.evaluate('dayRank(today())') == 'C'
    assert page.evaluate('completedPriorBasics("2026-10-14").length') == 2
    assert page.evaluate('completedStudies("2026-10-14").length') == 3
    assert page.evaluate('skillXP().paragraph') == 80  # Former main + separately earned extra.
    assert page.evaluate('baseEarned()') == 80 + 120 + 100 + 40 + 120
    assert page.evaluate('monthSummary(today()).problem') == 1
    before = page.evaluate('({xp:totals().earned,rank:completionPct(today()),plan:planCompliance(today(),today()),skill:skillXP(),boss:boss().raw,quest:weekQuestStatus(monday(today())).qs.find(q=>q.id==="extra").cur,week:weekCore(monday(today())).p,day:earnedByDay()[today()],morning:state.morningProtocol})')
    page.locator('#extraPanel summary').click()
    expect(page.locator('#extraTasks input[data-extra="paragraph"]')).to_be_visible()
    expect(page.locator('#extraTasks input[data-extra="problem"]')).to_be_visible()
    for key, xp in [('paragraph', 40), ('problem', 60)]:
        earned = page.evaluate('totals().earned')
        page.locator(f'#extraTasks input[data-extra="{key}"]').click()
        assert page.evaluate('totals().earned') == earned + xp
        expect(page.locator(f'#completedExtraTasks input[data-extra="{key}"]')).to_be_checked()
    after = page.evaluate('({xp:totals().earned,rank:completionPct(today()),plan:planCompliance(today(),today()),skill:skillXP(),boss:boss().raw,quest:weekQuestStatus(monday(today())).qs.find(q=>q.id==="extra").cur,week:weekCore(monday(today())).p,day:earnedByDay()[today()],morning:state.morningProtocol})')
    assert after['xp'] == before['xp'] + 100
    assert after['rank'] == before['rank'] and after['plan'] == before['plan']
    assert after['skill']['paragraph'] == before['skill']['paragraph'] + 40
    assert after['skill']['problem'] == before['skill']['problem'] + 60
    assert after['boss'] == before['boss'] + 2
    assert after['quest'] == before['quest'] + 100
    assert after['week'] == before['week'] + 100 and after['day'] == before['day'] + 100
    assert after['morning'] == before['morning']
    no_overflow(page)
    page.locator('#completedExtraTasks input[data-extra="paragraph"]').click()
    assert page.evaluate('totals().earned') == after['xp'] - 40
    assert page.evaluate('completionPct(today())') == before['rank']
    page.locator('#extraTasks input[data-extra="paragraph"]').click()
    page.evaluate("state.checks[checkKey(today(),'physics')]=true;save();render()")
    assert page.evaluate('completionPct(today())') == 100
    assert page.evaluate('dayRank(today())') == 'S'
    assert page.evaluate('planCompliance(today(),today()).pct') == 100
    assert page.evaluate('!state.checks[today()+"|paragraph"]&&!state.checks[today()+"|problem"]')
    assert page.evaluate('state.checks["2026-10-14|paragraph"]&&state.checks["2026-10-14|problem"]')
    plan_week(page, FUTURE)
    assert 'Paragraf' not in page.locator('#planDays').inner_text()
    assert 'Problem' not in page.locator('#planDays').inner_text()
    assert 'Paragraf/Problem' not in page.locator('#planSummary').inner_text()
    no_overflow(page)
    tab(page, 'backupTab')
    with page.expect_download() as info: page.locator('#export').click()
    backup = json.loads(Path(info.value.path()).read_text())
    for key, value in fixture['checks'].items(): assert backup['state']['checks'][key] == value
    page.locator('#import').set_input_files({'name': 'optional-backup.json', 'mimeType': 'application/json', 'buffer': json.dumps(backup).encode()})
    assert page.evaluate('state') == backup['state']
    page.reload(wait_until='networkidle')
    assert page.evaluate('state') == backup['state']
    no_overflow(page)
    page.context.close()
    print('PASS: optional Paragraph +40 / Problem +60 in Extra only; default/custom modern plans, weighted Rank/plan compliance, Skill Tree/Boss/quest/statistics, uncheck, legacy main XP plus distinct extra, Morning independence, JSON/reload and 360px.')

try:
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=shutil.which('chromium') or shutil.which('chromium-browser'), headless=True, args=['--no-sandbox'])
        test_optional_basics(browser)
        page = context(browser, initial=legacy)
        page.goto(URL, wait_until='networkidle')
        assert page.evaluate('state.planNotes') == {}
        assert page.evaluate('state.checks') == legacy['checks']
        assert page.evaluate('state.morningProtocol') == legacy['morningProtocol']
        assert not backend.calls, 'Offline students must not request separate note RPCs'
        original_metrics = metrics(page)
        print('PASS: legacy state loads without planNotes; historical checks and Morning Protocol preserved.')

        plan_week(page, FUTURE)
        note = 'Üçgende merkezlerden 20 soru çöz.\nYapamadıklarını işaretle.\n<img src=x onerror="window.noteInjected=true">\n' + 'uzunmetin' * 50
        add_lesson(page, FUTURE, 'geo', note)
        assert page.evaluate('state.planNotes["2026-10-19"].geo') == note
        expect(note_editor(page, FUTURE, 'geo')).to_contain_text(note)
        assert card(page, FUTURE).locator('.planAdd textarea').input_value() == ''
        no_overflow(page)
        tab(page, 'daily'); select_day(page, FUTURE)
        expect(page.locator('#tasks .planNote')).to_contain_text(note)
        assert page.locator('#tasks input:enabled').count() == 0
        assert page.locator('.planNote img').count() == 0
        assert not page.evaluate('window.noteInjected||false')
        no_overflow(page)
        page.reload(wait_until='networkidle'); select_day(page, FUTURE)
        expect(page.locator('#tasks .planNote')).to_contain_text(note)
        assert metrics(page) == original_metrics, 'Optional notes must not affect scoring'

        plan_week(page, FUTURE)
        edit_note(page, FUTURE, 'geo', 'Güncellenmiş geometri notu')
        tab(page, 'daily'); select_day(page, FUTURE)
        expect(page.locator('#tasks .planNote')).to_contain_text('Güncellenmiş geometri notu')
        plan_week(page, FUTURE)
        editor = note_editor(page, FUTURE, 'geo'); editor.locator('summary').click()
        editor.get_by_role('button', name='Notu sil', exact=True).click()
        assert page.evaluate('state.planNotes["2026-10-19"]||{}') == {}
        assert page.evaluate('tasks("2026-10-19").includes("geo")')
        edit_note(page, FUTURE, 'geo', 'Dersle birlikte silinecek')
        card(page, FUTURE).get_by_role('button', name='Geometri Kaldır', exact=True).click()
        assert not page.evaluate('state.planNotes["2026-10-19"]?.geo')
        assert not page.evaluate('tasks("2026-10-19").includes("geo")')
        print('PASS: add/edit/delete note, daily display, future locks, XSS-safe long text, reload and 360px layout; deleting a note retains its lesson, removing a lesson deletes its note.')

        edit_note(page, FUTURE, 'hist', 'Tarih notu korunmalı')
        add_lesson(page, FUTURE, 'geo', 'Varsayılanda yok, silinmeli')
        card(page, FUTURE).get_by_role('button', name='Günü varsayılana sıfırla', exact=True).click()
        assert page.evaluate('state.planNotes["2026-10-19"]') == {'hist': 'Tarih notu korunmalı'}
        add_lesson(page, '2026-10-20', 'mat', 'Haftalık sıfırlamada kalkmalı')
        edit_note(page, '2026-10-20', 'geo', 'Geometri notu korunmalı')
        page.locator('#resetPlanWeek').click()
        assert page.evaluate('state.planNotes["2026-10-20"]') == {'geo': 'Geometri notu korunmalı'}
        assert page.evaluate('state.planNotes["2026-10-19"].hist') == 'Tarih notu korunmalı'
        print('PASS: day/week reset removes notes only for removed lessons and retains remaining lesson notes.')

        plan_week(page, '2026-10-12')
        edit_note(page, TODAY, 'geo', 'Bugünkü geometri çalışması')
        edit_note(page, TODAY, 'mat', 'Fonksiyonlardan test 4\'ü çöz.')
        tab(page, 'daily'); select_day(page, TODAY)
        geo_task = page.locator('#tasks .task').filter(has_text='Bugünkü geometri çalışması')
        geo_task.locator('input').check()
        expect(geo_task).to_have_class('task done')
        expect(geo_task.locator('.planNote')).to_contain_text('Bugünkü geometri çalışması')
        page.locator('#openSwap').click(); page.locator('#swapOut').select_option('mat'); page.locator('#swapIn').select_option('bio'); page.locator('#saveSwap').click()
        swap_task = page.locator('#tasks .task').filter(has=page.locator('.swapTag'))
        expect(swap_task).to_contain_text('📝 TYT Matematik plan notu')
        expect(swap_task).to_contain_text("Fonksiyonlardan test 4'ü çöz.")
        expect(swap_task.locator('.xp')).to_have_text('+90 XP')
        assert not page.evaluate("savePlanNote(today(),'paragraph','yasak')")
        assert not page.evaluate("savePlanNote(today(),'problem','yasak')")
        assert not page.evaluate("savePlanNote(today(),'extra:bio','yasak')")
        page.locator('#extraPanel summary').click(); page.locator('#extraTasks input[data-extra="bio"]').click()
        assert page.locator('#completedExtraTasks .planNote,#extraTasks .planNote').count() == 0
        no_overflow(page)
        plan_week(page, '2026-10-12')
        edit_note(page, TODAY, 'geo', 'Tamamlandıktan sonra da düzenlenebilir')
        locked_plan = page.evaluate('state.weekPlans["2026-10-12"][today()]')
        page.locator('#resetPlanWeek').click()
        assert page.evaluate('state.weekPlans["2026-10-12"][today()]') == locked_plan
        assert page.evaluate('state.planNotes[today()].geo') == 'Tamamlandıktan sonra da düzenlenebilir'
        print('PASS: completed tasks keep notes; Swap retains original Mathematics note, Extra/Paragraph/Problem reject notes, locked-day plan remains unchanged.')

        tab(page, 'backupTab')
        with page.expect_download() as info: page.locator('#export').click()
        backup = json.loads(Path(info.value.path()).read_text())
        assert backup['state']['planNotes'] == page.evaluate('state.planNotes')
        raw_backup = json.dumps(backup)
        assert OWNER not in raw_backup and COACH not in raw_backup
        page.evaluate("savePlanNote(today(),'mat','İçe aktarma ile değişecek')")
        page.locator('#import').set_input_files({'name': 'test-backup.json', 'mimeType': 'application/json', 'buffer': json.dumps(backup).encode()})
        assert page.evaluate('state') == backup['state']
        assert page.evaluate('emptyState().planNotes') == {}
        page.locator('#reset').click()
        assert page.evaluate('state.planNotes') == {}
        page.locator('#import').set_input_files({'name': 'test-backup.json', 'mimeType': 'application/json', 'buffer': json.dumps(backup).encode()})
        assert page.evaluate('state') == backup['state']
        page.reload(wait_until='networkidle')
        assert page.evaluate('state') == backup['state']
        print('PASS: JSON export/import, full reset, localStorage and reload preserve the complete compatible student state.')

        backend.state = page.evaluate('state')
        owner = context(browser, 'owner'); owner.goto(URL, wait_until='networkidle')
        plan_week(owner, '2026-10-12')
        edit_note(owner, TODAY, 'mat', 'Diğer cihaza gidecek plan notu')
        owner.clock.run_for(600)
        owner.wait_for_function("document.getElementById('cloudStatus').textContent==='Kaydedildi'")
        assert backend.state['planNotes'][TODAY]['mat'] == 'Diğer cihaza gidecek plan notu'
        assert backend.state['checks']['2026-10-14|paragraph'] and backend.state['checks']['2026-10-14|problem']
        tab(owner, 'backupTab'); owner.locator('#syncNow').click()
        owner2 = context(browser, 'owner'); owner2.goto(URL, wait_until='networkidle')
        expect(owner2.locator('#tasks')).to_contain_text('Diğer cihaza gidecek plan notu')
        coach = context(browser); coach.goto(URL + '#coach=' + COACH, wait_until='networkidle')
        expect(coach.locator('#tasks')).to_contain_text('Diğer cihaza gidecek plan notu')
        expect(coach.locator('#cloudRole')).to_have_text('Koç · Salt okunur')
        plan_week(coach, '2026-10-12')
        expect(note_editor(coach, TODAY, 'mat')).to_contain_text('Diğer cihaza gidecek plan notu')
        assert coach.locator('.planNoteEditor').count() == 0
        assert coach.locator('.planAdd textarea:enabled,.planAdd button:enabled,.planRow button:enabled').count() == 0
        before, calls = coach.evaluate('state'), len(backend.calls)
        coach.evaluate("savePlanNote(today(),'mat','yasak');addPlannedLesson(today(),'physics','yasak');removePlannedLesson(today(),'geo');resetDayPlan(today());resetWeekPlan();writePlanNote(today(),'mat','yasak');prunePlanNotes(today(),[]);setMorningCheck(today(),'wake',true);buyReward('burger');saveSelectedCheckin(1,1,'yasak');save()")
        assert coach.evaluate('state') == before
        assert len(backend.calls) == calls
        assert not backend.unexpected, backend.unexpected
        assert {name for name, _ in backend.calls} <= {'get_yks_rpg_owner_state', 'get_yks_rpg_coach_state', 'save_yks_rpg_state'}
        for key in ['daily', 'rpg', 'mockTab', 'planTab', 'radarTab', 'statsTab', 'shopTab', 'backupTab']:
            tab(owner2, key); no_overflow(owner2)
            tab(coach, key); no_overflow(coach)
        print('PASS: automatic/manual existing state sync, second device and coach view; coach stays fully readonly; only the three original RPCs are used; all tabs fit 360px.')

        if args.baseline:
            snapshots=[]
            for source in [args.baseline.read_text(), (repo/'index.html').read_text()]:
                baseline_page=context(browser);page=baseline_page;c=page.context
                page.route(URL,lambda r,_request,html=source:r.fulfill(body=html,content_type='text/html'))
                page.goto(URL,wait_until='networkidle')
                snapshots.append(page.evaluate("""() => {
                    const results=[];
                    for(let seed=0;seed<12;seed++){
                        state=emptyState();
                        state.purchases=2;state.spentRests=1;state.rests['2026-10-05']=true;
                        state.rewardBuys=[{type:'shield',price:2000,date:'2026-10-01T06:00:00Z'}];
                        state.shieldUses['2026-10-09']=true;
                        state.chestClaims['2026-09-28']={tier:'Gold',reward:200,date:'2026-10-04T16:00:00Z'};
                        state.checkins['2026-10-10']={load:3,satisfaction:4,note:'Eski kayıt'};
                        state.weekPlans={'2026-10-12':{'2026-10-14':['geo','physics'],'2026-10-15':['mat','bio','geo']}};
                        state.swaps['2026-10-15']={outKey:'mat',inKey:'bio'};
                        state.mockExams=[{id:'legacy-mock-'+seed,date:'2026-10-14',type:'TYT',name:'Eski deneme',scores:{math:{correct:30,wrong:8}}}];
                        for(const day of trackedDates()){
                            const fixtureTasks=day<FLOW_START?tasks(day):['paragraph','problem',...(state.weekPlans[monday(day)]?.[day]||PLAN[idx(day)].filter(k=>!['tyt','r1','r2',...ANALYSIS_KEYS].includes(k)))];
                            for(const [i,k] of fixtureTasks.entries())if((parse(day).getDate()+i+seed)%4!==0)state.checks[checkKey(day,k)]=true;
                            if(day>=FLOW_START)for(const [i,k] of EXTRA_KEYS.entries())if((i+seed)%3===0)state.checks[checkKey(day,extraKey(k))]=true;
                            if((parse(day).getDate()+seed)%3===0)state.morningProtocol[day]={checks:Object.fromEntries(MORNING_STEPS.map(x=>[x.key,true])),timestamps:{firstQuestion:day+'T06:00:00Z'}};
                        }
                        state=normalizeRemoteState(JSON.parse(JSON.stringify(state)));migrateLegacyAnalysis();
                        const student=JSON.parse(JSON.stringify(state));delete student.planNotes;results.push({state:student,base:baseEarned(),skills:skillXP(),studies:allCompletedTaskCount(),morning:morningStatistics(),priorWeek:weekCore('2026-10-05'),priorMonth:monthSummary('2026-09-30'),priorPlan:planCompliance(START,'2026-10-13'),priorBonusDates:{srank:sRankDates('2026-10-13'),comeback:comebackDates('2026-10-13'),perfect:perfectWeekCount('2026-10-13')},days:trackedDates('2026-10-13').map(s=>({s,tasks:tasks(s),pct:completionPct(s),rank:dayRank(s)}))});
                    }
                    return results;
                }"""))
                c.close()
            assert snapshots[0]==snapshots[1], 'previous-version state or computed metrics changed'
            print('PASS: 12 previous-version fixtures preserve full state, earned task XP, Skill Tree, study counts, Morning and all checked pre-Oct-14 plans, Rank, bonuses and weekly/monthly XP metrics.')
        assert not errors, errors
        browser.close()
finally:
    for ctx in contexts:
        try: ctx.close()
        except Exception: pass
    server.shutdown()

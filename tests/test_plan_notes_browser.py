"""Plan-note browser tests. All cloud RPCs use an isolated in-memory state."""
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
    'checks': {'2026-10-05|tyt': True, '2026-10-10|geo': True},
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

try:
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=shutil.which('chromium') or shutil.which('chromium-browser'), headless=True, args=['--no-sandbox'])
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
                            for(const [i,k] of tasks(day).entries())if((parse(day).getDate()+i+seed)%4!==0)state.checks[checkKey(day,k)]=true;
                            if(day>=FLOW_START)for(const [i,k] of EXTRA_KEYS.entries())if((i+seed)%3===0)state.checks[checkKey(day,extraKey(k))]=true;
                            if((parse(day).getDate()+seed)%3===0)state.morningProtocol[day]={checks:Object.fromEntries(MORNING_STEPS.map(x=>[x.key,true])),timestamps:{firstQuestion:day+'T06:00:00Z'}};
                        }
                        state=normalizeRemoteState(JSON.parse(JSON.stringify(state)));migrateLegacyAnalysis();
                        const student=JSON.parse(JSON.stringify(state));delete student.planNotes;results.push({state:student,totals:totals(),skills:skillXP(),boss:boss(),streak:currentAndBestStreak(),morning:morningStatistics(),long:longProgress(),month:monthSummary(today()),quests:weekQuestStatus(monday(today())),radar:radarData(),days:trackedDates().map(s=>({s,tasks:tasks(s),pct:completionPct(s),rank:dayRank(s)}))});
                    }
                    return results;
                }"""))
                c.close()
            assert snapshots[0]==snapshots[1], 'previous-version state or computed metrics changed'
            print('PASS: 12 historical/current previous-version fixtures preserve state, XP, weighted/legacy Rank, Swap, Extra, Skill Tree, Boss, quests, main/morning streak, mock records, radar and long-term statistics.')
        assert not errors, errors
        browser.close()
finally:
    for ctx in contexts:
        try: ctx.close()
        except Exception: pass
    server.shutdown()

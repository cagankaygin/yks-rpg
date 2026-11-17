"""Rename vault books without changing linked question records. No real student/cloud data is used."""
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
fixture['questionVault']['books'] += [{'id':'other','name':'Diğer Kaynak','subject':'physics','createdAt':'2026-10-01'}, {'id':'unicode','name':'FİZİK Çalışması','subject':'chem','createdAt':'2026-10-02'}]
fixture['questionVault']['books'][0].update({'totalUnits':100,'completedUnits':40,'progressUnit':'test','progressUpdatedAt':'2026-11-16'})
for i,q in enumerate(fixture['questionVault']['questions']): q['difficulty']=['medium','hard','brutal'][i]
fixture['teacherQuestions']=[{'id':'ask-1','bookId':'book','topic':'Çember','page':'45','questionNo':'9','note':'Hocaya sor','addedAt':'2026-11-16'}]
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
def no_overflow(page):
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'), page.evaluate('Array.from(document.querySelectorAll("body *")).filter(e=>e.getBoundingClientRect().right>innerWidth+1).map(e=>[e.tagName,e.id,e.className,Math.round(e.getBoundingClientRect().right)]).slice(0,18)')
def start(page, key):
    page.locator('#studyTimerStart').click()
    no_overflow(page)
    page.locator(f'[data-study-task="{key}"]').click()
def non_timer(page): return page.evaluate('Object.fromEntries(Object.entries(state).filter(([key])=>key!=="studyTimer"))')
def gameplay(page): return page.evaluate('({xp:totals(),rank:dayRank(today()),pct:completionPct(today()),boss:boss(),streak:currentAndBestStreak(),quest:weekQuestStatus(monday(today()))})')
def choose(page, day):
    page.locator('#date').fill(day); page.locator('#date').dispatch_event('change')



def edit(page, book='book', container='#vaultBookMap'):
    page.locator(f'{container} [data-rename-book="{book}"]').click()
def save_name(page, name):
    page.locator('#vaultBookRenameInput').fill(name)
    page.locator('#vaultBookRenameForm button[type="submit"]').click()
def snapshot(page): return page.evaluate('state')
def unchanged_except_name(before,after,name):
    expected=copy.deepcopy(before)
    expected['questionVault']['books'][0]['name']=name
    assert after==expected

try:
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=shutil.which('chromium') or shutil.which('chromium-browser'),headless=True,args=['--no-sandbox'])
        page=context(browser,fixture);page.locator('[data-tab="vaultTab"]').click()
        initial=snapshot(page);initial_xp=gameplay(page)
        assert page.locator('#vaultBookMap [data-rename-book]').count()==3
        edit(page)
        expect(page.locator('#vaultBookRenameInput')).to_have_value('Eski geometri')
        page.locator('#vaultBookRenameInput').fill('Kaydedilmeyecek');page.locator('#cancelVaultBookRename').click()
        assert snapshot(page)==initial
        edit(page);save_name(page,'  Yeni   Geometri Kaynağı  ')
        expect(page.locator('#vaultBookRenameModal')).to_be_hidden()
        unchanged_except_name(initial,snapshot(page),'Yeni Geometri Kaynağı')
        assert gameplay(page)==initial_xp
        expect(page.locator('#vaultBookMap [data-vault-book-id="book"]')).to_contain_text('Yeni Geometri Kaynağı')
        expect(page.locator('#vaultQuestionBook option[value="book"]')).to_contain_text('Yeni Geometri Kaynağı')
        expect(page.locator('#vaultFilterBook option[value="book"]')).to_contain_text('Yeni Geometri Kaynağı')
        expect(page.locator('#vaultDueList')).to_contain_text('Yeni Geometri Kaynağı')
        page.locator('#vaultReadyDetails').evaluate('(el)=>el.open=true')
        expect(page.locator('#vaultReadyList')).to_contain_text('Yeni Geometri Kaynağı')
        page.locator('#quickVaultFab').click()
        expect(page.locator('#quickVaultBook option[value="book"]')).to_contain_text('Yeni Geometri Kaynağı')
        page.locator('#closeQuickVault').click();page.locator('[data-tab="teacherTab"]').click()
        expect(page.locator('#teacherQuestionBook option[value="book"]')).to_contain_text('Yeni Geometri Kaynağı')
        expect(page.locator('#teacherQuestionGroups')).to_contain_text('Yeni Geometri Kaynağı')
        page.locator('[data-tab="vaultTab"]').click()
        print('PASS: pencil buttons on existing source cards; cancel/save; name updates ready/due question references, filters, quick-add and teacher views. Only book.name changes: ID, questions, difficulty, reviews, mastery, source progress, XP and unrelated state stay exact.')

        saved=snapshot(page)
        for duplicate in ['Diğer Kaynak','   diğer   kaynak   ','FI\u0307ZI\u0307K Çalışması']:
            edit(page);save_name(page,duplicate)
            expect(page.locator('#vaultBookRenameNotice')).to_contain_text('zaten kayıtlı')
            assert snapshot(page)==saved
            page.locator('#cancelVaultBookRename').click()
        edit(page);save_name(page,'   ')
        expect(page.locator('#vaultBookRenameNotice')).to_contain_text('1–160')
        assert snapshot(page)==saved
        page.locator('#cancelVaultBookRename').click()
        assert page.evaluate('renameVaultBook("book","x".repeat(161))') is False
        assert snapshot(page)==saved
        # Rename to one's own case-insensitive name remains allowed.
        edit(page);save_name(page,'YENİ GEOMETRİ KAYNAĞI')
        assert page.evaluate('vaultBook("book").id')=='book'
        # Both add and edit reject case/spacing/canonical-Unicode duplicates across subjects.
        before_add=snapshot(page)
        page.locator('#vaultBookSubject').select_option('bio')
        page.locator('#vaultBookName').fill('  yeni   geometri kaynağı  ')
        page.locator('#vaultBookForm button[type="submit"]').click()
        assert snapshot(page)==before_add
        no_overflow(page)
        print('PASS: no blank/oversized names, no duplicate name on add or rename across subjects; Turkish case, whitespace and Unicode normalization; own-name case changes allowed. No old sources are merged or deleted.')

        # A rename during a review preserves the in-progress session and all records.
        page.evaluate('startVaultSession(["old-due"])')
        session_ids=page.evaluate('vaultSessionIds')
        edit(page)
        literal='<img src=x onerror="window.renameXss=true"> Kaynak'
        before=snapshot(page);save_name(page,literal)
        unchanged_except_name(before,snapshot(page),literal)
        assert page.evaluate('vaultSessionIds')==session_ids
        expect(page.locator('#vaultSessionSub')).to_contain_text(literal)
        assert page.locator('#vaultBookMap img').count()==0
        assert page.evaluate('window.renameXss===true') is False
        no_overflow(page)
        edit(page);save_name(page,'Güncel Geometri')
        saved=snapshot(page)
        page.reload(wait_until='networkidle');assert snapshot(page)==saved
        page.locator('[data-tab="backupTab"]').click()
        with page.expect_download() as download:page.locator('#export').click()
        backup=json.loads(Path(download.value.path()).read_text());assert backup['state']==saved
        page.locator('#import').set_input_files({'name':'rename.json','mimeType':'application/json','buffer':json.dumps(backup).encode()})
        assert snapshot(page)==saved
        print('PASS: active review stays on the same question, literal HTML is safely rendered as text, 360px layout, localStorage reload and JSON export/import preserve the rename and all linked data.')

        # Old duplicate books are retained on load; new edits still cannot add duplicates.
        legacy=copy.deepcopy(fixture)
        legacy['questionVault']['books'].append({'id':'legacy-duplicate','name':'Eski geometri','subject':'bio','createdAt':'2026-10-01'})
        old=context(browser,legacy)
        assert old.evaluate('vaultBooks().length')==4
        assert old.evaluate('vaultBook("book").id')=='book'
        assert old.evaluate('vaultBook("legacy-duplicate").id')=='legacy-duplicate'
        cloud=copy.deepcopy(saved)
        owner=context(browser,owner=True);owner.locator('[data-tab="vaultTab"]').click()
        before=snapshot(owner);edit(owner);save_name(owner,'Buluttaki Yeni Kaynak');advance(owner,1)
        expect(owner.locator('#cloudStatus')).to_have_text('Kaydedildi')
        unchanged_except_name(before,cloud,'Buluttaki Yeni Kaynak')
        second=context(browser,owner=True)
        assert second.evaluate('vaultBook("book").name')=='Buluttaki Yeni Kaynak'
        assert second.evaluate('state.questionVault.questions')==saved['questionVault']['questions']
        coach=context(browser,coach=True);advance(coach,1);coach.locator('[data-tab="vaultTab"]').click()
        expect(coach.locator('#vaultBookMap')).to_contain_text('Buluttaki Yeni Kaynak')
        assert coach.locator('[data-rename-book]').count()==0
        before=snapshot(coach)
        coach.evaluate('openVaultBookRename("book");renameVaultBook("book","Yetkisiz değişiklik");saveVaultBookRename({preventDefault(){}})')
        assert snapshot(coach)==before
        expect(coach.locator('#vaultBookRenameModal')).to_be_hidden()
        for item in [owner,second,coach]:no_overflow(item)
        assert not errors,errors
        print('PASS: existing duplicate legacy IDs survive load; same state JSON/RPC sync to second device; coach sees new names but has no pencil controls and cannot rename; no JS errors or new schema/storage keys.')
        browser.close()
finally:
    for ctx in contexts:
        try:ctx.close()
        except Exception:pass
    server.shutdown()

"""Isolated Chromium tests: all Supabase RPCs are mocked; no live data is used."""
import argparse
import copy
import functools
import http.server
import json
import shutil
import threading
import urllib.request
from pathlib import Path
from datetime import datetime,timezone,timedelta
from playwright.sync_api import sync_playwright,expect
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--supabase-js', type=Path, help='Optional local Supabase browser library')
parser.add_argument('--baseline', type=Path, help='Optional previous index.html for V3.4 comparison')
args = parser.parse_args()
repo = Path(__file__).resolve().parents[1]
class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_): pass
server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(QuietHandler, directory=str(repo)))
threading.Thread(target=server.serve_forever, daemon=True).start()
URL=f'http://127.0.0.1:{server.server_port}/'
CDN='https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2'
LIBRARY=args.supabase_js.read_bytes() if args.supabase_js else urllib.request.urlopen(CDN,timeout=30).read()
KEY='yks-xp-final-v1'
OWNER='test-only-owner-not-real-1234567890123456'
COACH='test-only-coach-not-real-1234567890123456'
base={'checks':{'2026-10-15|swap:mat:bio':True,'2026-10-15|bio':True},'rests':{},'purchases':0,'refunds':0,'spentRests':0,'rewardBuys':[],'shieldUses':{},'chestClaims':{},'checkins':{},'claimedAchievements':{},'coupons':0,'streakRewardUnlocked':False,'swaps':{'2026-10-15':{'outKey':'mat','inKey':'bio'}},'mockExams':[],'settings':{'examDate':'2027-06-19','morningWakeTime':'06:30','studyStartTime':'09:00'},'weekPlans':{'2026-10-12':{'2026-10-15':['mat','bio','geo']},'2026-10-19':{'2026-10-19':['geo','physics']}},'morningProtocol':{}}
class Backend:
    def __init__(self):
        self.state=copy.deepcopy(base);self.n=0;self.calls=[];self.read_error=False
        self.notes={'daily':{'2026-10-15':{'text':'İlk günlük koç notu','updatedAt':'2026-10-15T06:00:00Z'}},'lessons':{'2026-10-15':{'mat':{'text':'Matematik slotu için özel öneri','updatedAt':'2026-10-15T06:00:01Z'}},'2026-10-19':{'geo':{'text':'Üçgenler için 20 soru','updatedAt':'2026-10-15T06:00:02Z'}}},'updatedAt':'2026-10-15T06:00:02Z'}
    def stamp(self):self.n+=1;return (datetime(2026,10,15,7,tzinfo=timezone.utc)+timedelta(seconds=self.n)).isoformat()
    def request(self,route):
        r=route.request
        if r.method=='OPTIONS':return route.fulfill(status=200,headers={'access-control-allow-origin':'*','access-control-allow-headers':'*'})
        name=r.url.rsplit('/',1)[-1];body=r.post_data_json;self.calls.append((name,copy.deepcopy(body)))
        result=None;status=200
        if name=='get_yks_rpg_owner_state':result=[{'state':self.state,'updated_at':'2026-10-15T06:00:00Z'}] if body['raw_owner_token']==OWNER else []
        elif name=='get_yks_rpg_coach_state':result=[{'state':self.state,'updated_at':'2026-10-15T06:00:00Z'}] if body['raw_token']==COACH else []
        elif name=='save_yks_rpg_state':
            if body['raw_owner_token']!=OWNER:status=403;result={'code':'42501','message':'Invalid owner token'}
            else:self.state=copy.deepcopy(body['new_state']);result=self.stamp()
        elif name=='get_yks_rpg_coach_notes':
            if self.read_error:status=404;result={'code':'PGRST202','message':'Notes unavailable'}
            else:result=[{'coach_notes':self.notes,'updated_at':self.notes.get('updatedAt')}] if body['raw_token'] in [OWNER,COACH] else []
        elif name=='save_yks_rpg_coach_notes':
            if body['raw_coach_token']!=COACH:status=403;result={'code':'42501','message':'Invalid coach token'}
            else:
                patch=body['new_notes'];kind=next(iter(patch));day=next(iter(patch[kind]));key=None if kind=='daily' else next(iter(patch[kind][day]));value=patch[kind][day] if key is None else patch[kind][day][key]
                old=self.notes.get(kind,{}).get(day,{}) if key is None else self.notes.get(kind,{}).get(day,{}).get(key,{})
                if old.get('updatedAt')!=value['expectedUpdatedAt']:status=409;result={'code':'40001','message':'Note changed'}
                else:
                    stamp=self.stamp();note={'text':value['text'],'updatedAt':stamp}
                    if key is None:self.notes.setdefault(kind,{})[day]=note
                    else:self.notes.setdefault(kind,{}).setdefault(day,{})[key]=note
                    self.notes['updatedAt']=stamp;result=stamp
        else:raise AssertionError(name)
        route.fulfill(status=status,json=copy.deepcopy(result),headers={'access-control-allow-origin':'*'})
def ctx(browser,backend,role=None):
    c=browser.new_context(accept_downloads=True,timezone_id='Europe/Istanbul',viewport={'width':360,'height':900},reduced_motion='reduce')
    c.route(CDN,lambda r:r.fulfill(body=LIBRARY,content_type='application/javascript'));c.route('**/rest/v1/rpc/*',backend.request)
    if role=='owner':c.add_init_script(f"localStorage.setItem('yks-rpg-owner-token-v1',{json.dumps(OWNER)})")
    return c
def setup(page,errors):
    page.clock.install(time=datetime(2026,10,15,6,tzinfo=timezone.utc));page.on('pageerror',lambda e:errors.append(e.stack));page.on('dialog',lambda d:d.accept())
def select(page,day):page.locator('#date').fill(day);page.locator('#date').dispatch_event('change')
def tab(page,key):page.locator(f'[data-tab="{key}"]').click();expect(page.locator('#'+key)).to_be_visible()
def no_overflow(page):assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
def daily(page):return page.locator('#dailyCoachNotes .coachNoteEditor')
def lesson(page,day,key):return page.locator(f'.planCard[data-date="{day}"] .coachPlanNote[data-note-slot="{key}"]')
with sync_playwright() as p:
    b=p.chromium.launch(executable_path=shutil.which('chromium') or shutil.which('chromium-browser'),headless=True,args=['--no-sandbox']);backend=Backend()
    coach_ctx=ctx(b,backend);coach=coach_ctx.new_page();errors=[];setup(coach,errors);coach.goto(URL+'#coach='+COACH,wait_until='networkidle')
    expect(daily(coach).locator('textarea')).to_be_enabled();expect(coach).to_have_title('YKS RPG V3.5')
    student_before=copy.deepcopy(backend.state);client_before=coach.evaluate('state')
    assert coach.locator('#tasks input:enabled').count()==0;expect(coach.locator('#openSwap')).to_be_disabled()
    # All non-note entry points remain closed, even if a UI handler is invoked directly.
    coach.evaluate("claimChest();buyReward('burger');claimCoupon('none');saveSelectedCheckin(3,4,'forbidden');updateSwap(selected,'mat','geo',true);setDayPlan(today(),['chem']);setMorningCheck(today(),'wake',true);['rest','undoRest','useShield','undoShield','buy','refund','undoReward','clearCheckin','reset','forgetOwner'].forEach(id=>document.getElementById(id).onclick())")
    assert coach.evaluate('state')==client_before;assert backend.state==student_before
    assert not any(n=='save_yks_rpg_state' for n,_ in backend.calls)
    text='Koçun yeni günlük notu\n<img src=x onerror="window.notesInjected=true"> '+('uzunmetin'*90)
    daily(coach).locator('textarea').fill(text);daily(coach).get_by_role('button',name='Kaydet',exact=True).click()
    expect(daily(coach)).to_contain_text('✓ Koç notu kaydedildi');assert backend.notes['daily']['2026-10-15']['text']==text;assert backend.state==student_before;assert coach.evaluate('state')==client_before
    # Other dates can receive comments; this never unlocks student inputs.
    select(coach,'2026-10-14');daily(coach).locator('textarea').fill('Geçmiş gün notu');daily(coach).get_by_role('button',name='Kaydet',exact=True).click();expect(daily(coach)).to_contain_text('✓ Koç notu kaydedildi')
    select(coach,'2026-10-16');daily(coach).locator('textarea').fill('Gelecek gün notu');daily(coach).get_by_role('button',name='Kaydet',exact=True).click();expect(daily(coach)).to_contain_text('✓ Koç notu kaydedildi');assert coach.locator('#tasks input:enabled').count()==0
    tab(coach,'planTab');card=coach.locator('.planCard[data-date="2026-10-19"]');assert card.locator('.planRow button:enabled').count()==0;assert card.locator('.planAdd button:enabled').count()==0
    geo=lesson(coach,'2026-10-19','geo');geo.locator('summary').click();geo.locator('textarea').fill('Yeni geometri önerisi')
    # A regular refresh cannot destroy an in-progress note draft.
    coach.evaluate('loadCoachCloud()');expect(geo.locator('textarea')).to_have_value('Yeni geometri önerisi')
    geo.get_by_role('button',name='Kaydet',exact=True).click();expect(geo).to_contain_text('✓ Koç notu kaydedildi');assert backend.notes['lessons']['2026-10-19']['geo']['text']=='Yeni geometri önerisi'
    # Same-path concurrent updates are detected, server text and local draft both remain visible.
    geo.locator('textarea').fill('Yerel taslak korunmalı');backend.notes['lessons']['2026-10-19']['geo']={'text':'Başka oturumun daha yeni notu','updatedAt':backend.stamp()};backend.notes['updatedAt']=backend.notes['lessons']['2026-10-19']['geo']['updatedAt']
    geo.get_by_role('button',name='Kaydet',exact=True).click();expect(geo).to_contain_text('Not başka bir oturumda değişti');expect(geo.locator('textarea')).to_have_value('Yerel taslak korunmalı');expect(geo).to_contain_text('Başka oturumun daha yeni notu')
    geo.get_by_role('button',name='Güncel notu kullan',exact=True).click();expect(geo.locator('textarea')).to_have_value('Başka oturumun daha yeni notu')
    geo.locator('textarea').fill('Son geometri notu');geo.get_by_role('button',name='Kaydet',exact=True).click();expect(geo).to_contain_text('✓ Koç notu kaydedildi')
    assert backend.state==student_before;assert coach.evaluate('state')==client_before;no_overflow(coach)
    assert coach.evaluate(f"localStorage.getItem('{KEY}')") is None
    print('PASS: coach writes daily/past/future/lesson notes only; student mutations are blocked, drafts survive refresh, stale edits conflict without overwriting another note, 360px editor fits.')
    # Owner device one reads notes as plain text; no note write controls or secrets in state.
    owner_ctx=ctx(b,backend,'owner');owner=owner_ctx.new_page();setup(owner,errors);owner.goto(URL,wait_until='networkidle')
    expect(owner.locator('#dailyCoachNotes')).to_contain_text('Koçun yeni günlük notu');assert owner.locator('#dailyCoachNotes textarea').count()==0;assert owner.locator('.coachNoteText img').count()==0;assert not owner.evaluate('window.notesInjected||false')
    math=owner.locator('#tasks .task').filter(has=owner.locator('.swapTag'));expect(math).to_contain_text('💬 Koç · TYT Matematik plan notu');expect(math).to_contain_text('Matematik slotu için özel öneri')
    assert owner.locator('#extraTasks .lessonCoachNote,#completedExtraTasks .lessonCoachNote').count()==0
    assert not owner.evaluate("saveCoachNote(today(),null)")
    no_overflow(owner);assert owner.locator('#tasks .task.done .lessonCoachNote').count()>0
    expect(owner.locator('#coachNotesNew')).to_be_visible();tab(owner,'planTab');expect(lesson(owner,'2026-10-19','geo')).to_contain_text('Son geometri notu');expect(owner.locator('#coachNotesNew')).to_be_hidden()
    # Removing and adding a lesson never deletes its separate coach note.
    card=owner.locator('.planCard[data-date="2026-10-19"]');notes_before=copy.deepcopy(backend.notes)
    card.get_by_role('button',name='Geometri Kaldır',exact=True).click();assert lesson(owner,'2026-10-19','geo').count()==0
    assert backend.notes==notes_before
    card.locator('.planAdd select').select_option('geo');card.get_by_role('button',name='Ders ekle',exact=True).click();expect(lesson(owner,'2026-10-19','geo')).to_contain_text('Son geometri notu')
    # Normal owner sync preserves notes; note reads are separate from state JSON.
    tab(owner,'backupTab');owner.locator('#syncNow').click();owner.wait_for_timeout(700)
    assert backend.notes==notes_before
    # A manual sync waits for an older upload, then sends the latest local edits.
    owner.evaluate("""() => {
        const original=sb.rpc.bind(sb);window.deferNextStateSave=true;
        sb.rpc=async(name,args)=>{
            if(name==='save_yks_rpg_state'&&window.deferNextStateSave){
                window.deferNextStateSave=false;const snapshot=structuredClone(args);
                await new Promise(resolve=>window.releaseStudentUpload=resolve);
                return original(name,snapshot);
            }
            return original(name,args);
        };
        window.oldUpload=syncToCloud(false);
        state.checks[checkKey(today(),extraKey('chem'))]=true;save();
        window.manualUpload=syncStudentAndCoachNotes();
    }""")
    assert owner.evaluate('cloudBusy')
    owner.evaluate('async()=>{releaseStudentUpload();await oldUpload;await manualUpload}')
    assert backend.state['checks']['2026-10-15|extra:chem'] is True
    assert backend.notes==notes_before
    state_payloads=[body['new_state'] for name,body in backend.calls if name=='save_yks_rpg_state'];assert state_payloads
    assert all('coach_notes' not in state and 'coachNotes' not in state for state in state_payloads)
    with owner.expect_download() as info:owner.locator('#export').click()
    backup=json.loads(Path(info.value.path()).read_text());raw=json.dumps(backup)
    assert OWNER not in raw and COACH not in raw;assert 'coach_notes' not in backup['state'];assert 'coachNotes' not in backup['state']
    # Coach updates reach both student devices after note sync/reload.
    owner2_ctx=ctx(b,backend,'owner');owner2=owner2_ctx.new_page();setup(owner2,errors);owner2.goto(URL,wait_until='networkidle')
    tab(coach,'daily');select(coach,'2026-10-15');daily(coach).locator('textarea').fill('İki cihaz için güncel not');daily(coach).get_by_role('button',name='Kaydet',exact=True).click();expect(daily(coach)).to_contain_text('✓ Koç notu kaydedildi')
    owner.locator('#syncNow').click();owner.wait_for_timeout(700);tab(owner,'daily');expect(owner.locator('#dailyCoachNotes')).to_contain_text('İki cihaz için güncel not')
    owner2.reload(wait_until='networkidle');expect(owner2.locator('#dailyCoachNotes')).to_contain_text('İki cihaz için güncel not')
    # Delete general and lesson comments without changing any student fields.
    state_before=copy.deepcopy(backend.state);daily(coach).get_by_role('button',name='Notu sil',exact=True).click();expect(daily(coach)).to_contain_text('✓ Koç notu silindi');assert backend.notes['daily']['2026-10-15']['text']==''
    tab(coach,'planTab');geo=lesson(coach,'2026-10-19','geo');
    if not geo.locator('details').evaluate('(x)=>x.open'):geo.locator('summary').click()
    geo.get_by_role('button',name='Notu sil',exact=True).click();expect(geo).to_contain_text('✓ Koç notu silindi');assert backend.notes['lessons']['2026-10-19']['geo']['text']=='';assert backend.state==state_before
    coach.reload(wait_until='networkidle');assert coach.evaluate('state')==backend.state
    assert not errors,errors
    print('PASS: student readonly display, XSS-safe text, original Swap slot, no Extra notes, removed-plan-note retention, owner state/notes isolation, cross-device refresh, delete/reload, timestamp-only unread badge, no tokens/notes write data in student exports.')
    # Invalid coach / absent notes backend stays closed while existing student flows continue.
    bad_ctx=ctx(b,backend);bad=bad_ctx.new_page();setup(bad,errors);bad.goto(URL+'#coach=invalid-test-only',wait_until='networkidle');assert bad.locator('.coachNoteEditor textarea:enabled').count()==0;assert not bad.evaluate("saveCoachNote(today(),null)")
    backend.read_error=True;missing_ctx=ctx(b,backend,'owner');missing=missing_ctx.new_page();setup(missing,errors);missing.goto(URL,wait_until='networkidle');expect(missing.locator('#dailyCoachNotes')).to_contain_text('henüz etkin değil')
    assert missing.locator('#tasks input:enabled').count()>0
    for key in ['rpg','mockTab','planTab','radarTab','statsTab','shopTab','backupTab','daily']:
        tab(missing,key);no_overflow(missing)
    # Existing Extra UI and Morning Protocol stay independent of weighted Rank.
    before=missing.evaluate('({rank:completionPct(today()),xp:totals().earned,boss:boss().raw})')
    missing.locator('#completedExtraTasks input[data-extra="chem"]').click()
    expect(missing.locator('#completedExtraTasks input[data-extra="chem"]')).to_have_count(0)
    missing.locator('#extraPanel summary').click()
    missing.locator('#extraTasks input[data-extra="chem"]').click()
    expect(missing.locator('#completedExtraTasks')).to_contain_text('➕ EK')
    assert missing.evaluate('({rank:completionPct(today()),xp:totals().earned,boss:boss().raw})')==before
    missing.locator('#morningPanel summary').click()
    for i in range(6):missing.locator('#morningTasks input[type="checkbox"]').nth(i).check()
    expect(missing.locator('#morningState')).to_have_text('Tamamlandı')
    assert missing.evaluate('({rank:completionPct(today()),xp:totals().earned,boss:boss().raw})')==before
    assert len(missing.evaluate("JSON.parse(localStorage.getItem(KEY)).morningProtocol[today()].checks"))==6
    missing.evaluate('syncStudentAndCoachNotes()')
    missing.reload(wait_until='networkidle');expect(missing.locator('#morningProgress')).to_have_text('6 / 6')
    assert not errors,errors
    print('PASS: invalid coach and unavailable notes backend do not enable note writes; student study UI remains usable.')
    for c in [coach_ctx,owner_ctx,owner2_ctx,bad_ctx,missing_ctx]:c.close()
    if args.baseline:
        snapshots=[]
        for source in [args.baseline.read_text(), (repo/'index.html').read_text()]:
            c=ctx(b,backend);page=c.new_page();setup(page,errors)
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
                    results.push({state,totals:totals(),skills:skillXP(),boss:boss(),streak:currentAndBestStreak(),morning:morningStatistics(),long:longProgress(),month:monthSummary(today()),quests:weekQuestStatus(monday(today())),radar:radarData(),days:trackedDates().map(s=>({s,tasks:tasks(s),pct:completionPct(s),rank:dayRank(s)}))});
                }
                return results;
            }"""))
            c.close()
        assert snapshots[0]==snapshots[1], 'V3.4 state or computed metrics changed'
        print('PASS: 12 historical/current V3.4 fixtures preserve state, XP, weighted/legacy Rank, Swap, Extra, Skill Tree, Boss, quests, main/morning streak, mock records, radar and long-term statistics.')
    b.close()
    server.shutdown()

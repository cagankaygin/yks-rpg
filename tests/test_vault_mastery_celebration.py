"""First-mastery celebration, unchanged review schedule and persistence. RPCs are mocked."""
import argparse, copy, functools, http.server, json, shutil, threading, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--supabase-js',type=Path)
args=parser.parse_args()
root=Path(__file__).resolve().parents[1]
cdn='https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2'
library=args.supabase_js.read_bytes() if args.supabase_js else urllib.request.urlopen(cdn,timeout=30).read()
KEY='yks-xp-final-v1';TOKEN='synthetic-mastery-owner-test-only-12345'

def question(key,stage=2,mastered=False):
 return {'id':key,'sourceType':'mock','bookId':'','mockId':'','mockType':'TYT','mockName':'Eski deneme','mockDate':'2026-09-28',
         'subject':'geo','originStatus':'wrong','topic':'Üçgenler','page':'','questionNo':key,'addedAt':'2026-09-28','firstEligibleAt':'2026-10-05',
         'active':True,'successStage':stage,'lastResult':'solved','lastAttemptAt':'2026-10-19','nextDueAt':'' if mastered else '2026-11-16',
         'mastered':mastered,'history':[{'date':'2026-10-05','result':'solved'},{'date':'2026-10-19','result':'solved'}]}
legacy={'checks':{'2026-09-28|tyt':True},'rests':{},'purchases':1,
        'rewardBuys':[{'type':'burger','date':'2026-09-28T06:00:00Z','price':800,'couponUsed':False}],
        'questionVault':{'books':[],'questions':[question('already-mastered',3,True)]}}
class Quiet(http.server.SimpleHTTPRequestHandler):
 def log_message(self,*_):pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=str(root)))
threading.Thread(target=server.serve_forever,daemon=True).start()
url=f'http://127.0.0.1:{server.server_port}/';contexts=[];errors=[];cloud=copy.deepcopy(legacy)

def rpc(route):
 global cloud
 name=route.request.url.rsplit('/',1)[-1];body=route.request.post_data_json
 if name=='get_yks_rpg_owner_state' and body['raw_owner_token']==TOKEN:value=[{'state':cloud,'updated_at':'2026-11-16T06:00:00Z'}]
 elif name=='save_yks_rpg_state' and body['raw_owner_token']==TOKEN:cloud=copy.deepcopy(body['new_state']);value='2026-11-16T06:00:00Z'
 elif name=='get_yks_rpg_coach_state':value=[{'state':cloud,'updated_at':'2026-11-16T06:00:00Z'}]
 else:raise AssertionError('Unexpected RPC: '+name)
 route.fulfill(json=copy.deepcopy(value))
def context(browser,initial=None,day='2026-11-16',reduce=False,owner=False,coach=False):
 ctx=browser.new_context(viewport={'width':360,'height':900},timezone_id='Europe/Istanbul',accept_downloads=True,reduced_motion='reduce' if reduce else 'no-preference')
 contexts.append(ctx);ctx.route(cdn,lambda r:r.fulfill(body=library,content_type='application/javascript'));ctx.route('**/rest/v1/rpc/*',rpc)
 if initial is not None:ctx.add_init_script(f"if(!localStorage.getItem('{KEY}'))localStorage.setItem('{KEY}',{json.dumps(json.dumps(initial))})")
 if owner:ctx.add_init_script(f"localStorage.setItem('yks-rpg-owner-token-v1',{json.dumps(TOKEN)})")
 page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.on('dialog',lambda d:d.accept())
 now=datetime.fromisoformat(day+'T06:00:00+00:00');page.clock.install(time=now);page.clock.pause_at(now+timedelta(seconds=1))
 page.goto(url+('#coach=synthetic-test-only' if coach else ''),wait_until='networkidle')
 page.locator('[data-tab="vaultTab"]').click()
 return page

def set_day(page,day):
 page.clock.set_system_time(datetime.fromisoformat(day+'T06:00:00+00:00'));page.evaluate('renderQuestionVault()')
def summary(page):return page.locator('#vaultSummary .stat').filter(has_text='TOPLAM ÖĞRENİLEN').locator('b')
def getq(page,key):return page.evaluate('(id)=>vaultQuestions().find(q=>q.id===id)',key)
def no_overflow(page):assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')

try:
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path=shutil.which('chromium') or shutil.which('chromium-browser'),headless=True,args=['--no-sandbox'])
  page=context(browser,initial=legacy,day='2026-09-28')
  expect(page.locator('#vaultMasteryCelebration')).to_be_hidden();expect(summary(page)).to_have_text('1')
  assert 'masteryCelebratedAt' not in getq(page,'already-mastered')
  initial_xp=page.evaluate('totals()')
  page.locator('#vaultBookSubject').select_option('geo');page.locator('#vaultBookName').fill('Geometri testi');page.locator('#vaultBookForm button').click()
  book=page.evaluate('vaultBooks()[0].id');page.locator('#vaultQuestionBook').select_option(book);page.locator('#vaultQuestionTopic').fill('Üçgenler')
  page.locator('#vaultPage').fill('12');page.locator('#vaultQuestionNo').fill('3');page.locator('#vaultLearnedDate').fill('2026-09-28');page.locator('#vaultQuestionForm button').click()
  key=page.evaluate('vaultQuestions().find(q=>q.id!=="already-mastered").id')
  assert getq(page,key)['successStage']==0 and getq(page,key)['firstEligibleAt']=='2026-10-05'
  expect(page.locator('#vaultMasteryCelebration')).to_be_hidden()
  set_day(page,'2026-10-04');assert page.evaluate('vaultReadyQuestions().length')==0
  set_day(page,'2026-10-05');assert page.evaluate('vaultReadyQuestions().length')==1
  page.locator('#vaultReadyDetails summary').click();page.locator('#vaultReadyList input[type="checkbox"]').check();page.locator('#vaultStartSelected').click();page.locator('#vaultSolved').click()
  assert getq(page,key)['successStage']==1 and getq(page,key)['nextDueAt']=='2026-10-19'
  assert not getq(page,key)['mastered'] and 'masteryCelebratedAt' not in getq(page,key)
  expect(page.locator('#vaultMasteryCelebration')).to_be_hidden()
  set_day(page,'2026-10-18');assert page.evaluate('vaultDueQuestions().length')==0
  set_day(page,'2026-10-19');page.locator('#vaultStartDue').click();page.locator('#vaultSolved').click()
  assert getq(page,key)['successStage']==2 and getq(page,key)['nextDueAt']=='2026-11-16'
  expect(page.locator('#vaultMasteryCelebration')).to_be_hidden();expect(summary(page)).to_have_text('1')
  set_day(page,'2026-11-15');assert page.evaluate('vaultDueQuestions().length')==0
  set_day(page,'2026-11-16');page.locator('#vaultStartDue').click();page.locator('#vaultSolved').click()
  overlay=page.locator('#vaultMasteryCelebration');expect(overlay).to_be_visible()
  expect(overlay).to_contain_text('🎉 TEBRİKLER!');expect(overlay).to_contain_text('Bu soruyu tamamen öğrendin!')
  expect(overlay).to_contain_text('Bir zamanlar seni zorlayan bu soru artık öğrendiğin sorular arasında. Harika ilerleme! 🧠🔥')
  assert overlay.locator('.vaultMasteryConfetti i').count()==24
  learned=getq(page,key);assert learned['mastered'] and learned['successStage']==3 and learned['nextDueAt']==''
  assert len(learned['history'])==3 and learned['masteryCelebratedAt']
  expect(summary(page)).to_have_text('2');expect(page.locator('#vaultMasteredTotal')).to_have_text('2')
  assert page.evaluate('totals()')==initial_xp
  no_overflow(page);page.screenshot(path='/tmp/yks-mastery-celebration-360.png',animations='disabled')
  page.clock.run_for(3400);expect(overlay).to_be_visible();page.clock.run_for(100);expect(overlay).to_be_hidden()
  assert page.evaluate('vaultMasteryCelebrationTimer') is None
  page.reload(wait_until='networkidle');page.locator('[data-tab="vaultTab"]').click()
  expect(overlay).to_be_hidden();assert getq(page,key)['masteryCelebratedAt']==learned['masteryCelebratedAt']
  assert getq(page,key)['history']==learned['history'];assert page.evaluate('totals()')==initial_xp
  assert page.evaluate('state.checks')==legacy['checks']
  print('PASS: original 7/14/28-day path unchanged; video/first/second repeats do not celebrate; third solved repeat shows exact message, trophy and 24 confetti pieces for 3.5s; counts update, no XP gain, no reload replay.')

  # Stale repeats and a restored/regressed question with a persistent marker never celebrate twice.
  page.evaluate('(id)=>{vaultSessionIds=[id];vaultSessionIndex=0;recordVaultResult("solved")}',key)
  assert getq(page,key)['history']==learned['history'];expect(overlay).to_be_hidden()
  page.evaluate('(id)=>{const q=vaultQuestions().find(q=>q.id===id);q.mastered=false;q.successStage=2;q.nextDueAt=today();renderQuestionVault()}',key)
  page.locator('#vaultStartDue').click();page.locator('#vaultSolved').click();expect(overlay).to_be_hidden()
  assert getq(page,key)['masteryCelebratedAt']==learned['masteryCelebratedAt']
  page.locator('[data-tab="backupTab"]').click()
  with page.expect_download() as info:page.locator('#export').click()
  backup=json.loads(Path(info.value.path()).read_text())
  page.locator('#import').set_input_files({'name':'mastery.json','mimeType':'application/json','buffer':json.dumps(backup).encode()})
  assert getq(page,key)['masteryCelebratedAt']==learned['masteryCelebratedAt'];expect(overlay).to_be_hidden()
  assert page.evaluate('totals()')==initial_xp
  print('PASS: existing mastered imports do not replay, stale callbacks do not duplicate progress/XP, persistent first-mastery marker survives regression and JSON import/export.')

  for result,stage in [('partial',2),('failed',0)]:
   data=copy.deepcopy(legacy);data['questionVault']['questions'].append(question(result))
   test=context(browser,initial=data);test.locator('#vaultStartDue').click();test.locator('#vaultPartial' if result=='partial' else '#vaultFailed').click()
   q=getq(test,result);assert q['successStage']==stage and q['nextDueAt']=='2026-11-23' and not q['mastered']
   expect(test.locator('#vaultMasteryCelebration')).to_be_hidden();expect(summary(test)).to_have_text('1')
  # Two final-stage questions must both be shown; removing the first mastered item must not skip the second.
  data=copy.deepcopy(legacy);data['questionVault']['questions'] += [question('batch-a'),question('batch-b')]
  batch=context(browser,initial=data);batch.locator('#vaultStartDue').click();batch.locator('#vaultSolved').click()
  expect(batch.locator('#vaultMasteryCelebration')).to_be_visible();expect(batch.locator('#vaultSessionPanel')).to_be_visible()
  expect(batch.locator('#vaultSessionRef')).to_contain_text('batch-b')
  batch.locator('#closeVaultMasteryCelebration').click();expect(batch.locator('#vaultMasteryCelebration')).to_be_hidden()
  batch.locator('#vaultSolved').click();expect(batch.locator('#vaultMasteryCelebration')).to_be_visible();expect(summary(batch)).to_have_text('3')
  batch.keyboard.press('Escape');expect(batch.locator('#vaultMasteryCelebration')).to_be_hidden();batch.clock.run_for(4000)
  expect(batch.locator('#vaultMasteryCelebration')).to_be_hidden();no_overflow(batch)
  reduced=context(browser,initial=data,reduce=True);reduced.locator('#vaultStartDue').click();reduced.locator('#vaultSolved').click()
  expect(reduced.locator('#vaultMasteryCelebration')).to_be_visible()
  assert reduced.locator('#vaultMasteryConfetti i').count()==0
  assert reduced.locator('.vaultMasteryTrophy').evaluate('(el)=>getComputedStyle(el).animationName')=='none'
  reduced.clock.run_for(3500);expect(reduced.locator('#vaultMasteryCelebration')).to_be_hidden()
  print('PASS: partial/failure schedules unchanged; batch mastery does not skip the next question; immediate close/Escape; reduced-motion static success; mobile no overflow.')

  cloud=copy.deepcopy(backup['state']);cloud['questionVault']['questions'].append(question('sync-final'))
  owner=context(browser,owner=True);owner.locator('#vaultStartDue').click();xp=owner.evaluate('totals()');owner.locator('#vaultSolved').click()
  owner.clock.run_for(600);owner.wait_for_function("document.getElementById('cloudStatus').textContent==='Kaydedildi'")
  synced=next(q for q in cloud['questionVault']['questions'] if q['id']=='sync-final');assert synced['masteryCelebratedAt']
  assert owner.evaluate('totals()')==xp
  second=context(browser,owner=True);expect(second.locator('#vaultMasteryCelebration')).to_be_hidden();expect(summary(second)).to_have_text('3')
  assert getq(second,'sync-final')['masteryCelebratedAt']==synced['masteryCelebratedAt']
  coach=context(browser,coach=True);before=coach.evaluate('state');coach.evaluate('startVaultSession(["sync-final"]);recordVaultResult("solved")')
  assert coach.evaluate('state')==before;expect(coach.locator('#vaultMasteryCelebration')).to_be_hidden()
  expect(summary(coach)).to_have_text('3');assert not errors,errors
  print('PASS: existing state Sync carries mastery timestamp/count; second device/coach load never replays; coach readonly; no JS errors; no new storage key, table, RPC or XP award.')
  browser.close()
finally:
 for ctx in contexts:
  try:ctx.close()
  except Exception:pass
 server.shutdown()

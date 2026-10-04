from datetime import datetime, timezone
from src.backend import calling_times as clocks
from pathlib import Path
import json
import shutil
import subprocess

def instant(text):
    return datetime.fromisoformat(text.replace('Z', '+00:00'))

def test_city_resolution_keeps_split_zone_unknowns_and_exceptions():
    for city, state, expected in [
        ('Windsor','ON','America/Toronto'), ('Dryden','ON','America/Winnipeg'),
        ('Atikokan','ON','America/Atikokan'), ('Phoenix','AZ','America/Phoenix'),
        ('Francesville','IN','America/New_York'), ('Gary','IN','America/Chicago'),
        ('West Wendover','NV','America/Denver'), ('Unknown Town','ON',None),
        ('Unknown Town','AZ',None), ('Nashville','TN','America/Chicago'),
    ]:
        assert clocks.zone_for({'city':city,'state_prov':state}) == expected
    assert clocks.zone_for({'city':'Windsor','state_prov':'ON','country':'GB'}) is None

def test_office_window_boundaries_weekends_and_seasonal_rules():
    assert not clocks.within_hours('America/Toronto', instant('2026-10-05T12:59:00Z'))
    assert clocks.within_hours('America/Toronto', instant('2026-10-05T13:00:00Z'))
    assert not clocks.within_hours('America/Toronto', instant('2026-10-05T21:00:00Z'))
    assert not clocks.within_hours('America/Toronto', instant('2026-10-03T16:00:00Z'))
    assert not clocks.within_hours(None)
    summer = clocks.clock_data(instant('2026-07-01T16:00:00Z'))['zones']
    winter = clocks.clock_data(instant('2026-12-01T16:00:00Z'))['zones']
    assert summer['America/Toronto']['offset'] == -240
    assert winter['America/Toronto']['offset'] == -300
    assert summer['America/Phoenix']['offset'] == winter['America/Phoenix']['offset'] == -420
    assert winter['America/Vancouver']['offset'] == -420
    assert winter['America/Winnipeg']['offset'] == -300
    assert winter['America/Los_Angeles']['offset'] == -480

def test_live_browser_clock_search_formats_and_stale_guard():
    source = (Path(__file__).resolve().parents[1] / 'src/frontend/static/js/calling-times.js').read_text(encoding='utf-8')
    script = r'''
const vm=require('node:vm'), assert=require('node:assert/strict');
let wall=Date.parse('2026-10-05T13:00:00Z'), mono=1000, callback, store, fail=false;
const listeners={}, saved=new Map();
class FakeDate extends Date { static now(){return wall;} }
const context={window:{addEventListener:(n,fn)=>listeners[n]=fn},
 document:{hidden:false,getElementById:()=>({textContent:'{"id":1}'}),addEventListener:(n,fn)=>{if(n==='alpine:init')callback=fn;else listeners[n]=fn;}},
 Alpine:{store:(name,value)=>{if(value)store=value;return store;}},
 localStorage:{getItem:k=>saved.get(k),setItem:(k,v)=>saved.set(k,v)}, location:{search:''},
 Date:FakeDate,Intl,URLSearchParams,AbortController,performance:{now:()=>mono},setTimeout:()=>1,clearTimeout:()=>{},setInterval:()=>1,
 fetch:async()=>{if(fail)throw new Error('offline');return {ok:true,json:async()=>({at:'2026-10-05T13:00:00Z',zones:{'America/Toronto':{offset:-240,name:'Eastern · Canada'}}})};}};
vm.createContext(context);vm.runInContext(SOURCE,context);context.callingTimes=context.window.callingTimes;
const helpers=context.callingTimes;callback();
(async()=>{
 assert(helpers.matches('Ontario ON Windsor',' on '));
 assert(!helpers.matches('Washington Washington DC Montana','ON'));
 assert(helpers.matches('Quebec QC Montréal','montreal'));
 assert(helpers.matches('Ontario ON Windsor Eastern Canada','eastern canada'));
 assert(!helpers.matches('Ontario ON Windsor','texas'));
 await store.init();
 assert(store.fresh);assert(store.info('America/Toronto').good);
 const first=store.info('America/Toronto').clock;
 mono+=1000;wall+=1000;store.tick();
 assert.notEqual(store.info('America/Toronto').clock,first);
 assert.match(store.info('America/Toronto').clock,/AM/);
 store.setFormat('24');assert(!/AM|PM/.test(store.info('America/Toronto').clock));
 assert.equal(store.hourLabel(17),'17:00');assert.match(store.indiaWindow('America/Toronto'),/18:30/);
 store.setFormat('12');assert.equal(store.hourLabel(17),'5:00 PM');assert.match(store.indiaWindow('America/Toronto'),/6:30 PM/);
 assert.equal(helpers.status({day:1,hour:16,minute:30},9,17),'Closing soon');
 assert.equal(helpers.status({day:1,hour:17,minute:0},9,17),'Outside calling hours');
 assert.equal(helpers.status({day:6,hour:10,minute:0},9,17),'Outside calling hours · Weekend');
 fail=true;mono+=121000;wall+=121000;store.tick();await new Promise(resolve=>setImmediate(resolve));
 assert(!store.fresh);assert(!store.info('America/Toronto').good);assert.equal(store.info('America/Toronto').kind,'unknown');
 assert.match(store.indiaNow(),/Waiting/);
 fail=false;await store.refresh();assert(store.fresh);
 wall+=60000;assert(!store.fresh);assert(!store.info('America/Toronto').good);
 await store.refresh();listeners.focus();
 assert(!store.fresh);await new Promise(resolve=>setImmediate(resolve));assert(store.fresh);
})().catch(e=>{console.error(e);process.exitCode=1;});
'''.replace('SOURCE',json.dumps(source))
    result = subprocess.run([shutil.which('node') or r'C:\Program Files\nodejs\node.exe','-'],input=script,encoding='utf-8',capture_output=True)
    assert result.returncode == 0, result.stderr

"""Workflow checks use isolated data and a dependency-free JavaScript harness."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import shutil
import sqlite3
import subprocess

from fastapi.testclient import TestClient
from src.backend.main import app
from src.backend.db.queries import log_outreach_call


def test_follow_up_windows_sort_before_pagination(tmp_path, monkeypatch, session_test_db):
    database = tmp_path / "workflow.db"
    shutil.copy2(session_test_db, database)
    monkeypatch.setenv("FREIGHT_DB_PATH", str(database))
    with sqlite3.connect(database) as conn:
        conn.execute("UPDATE prospect_engagement_state SET next_follow_up_at=NULL")
    local = timezone(timedelta(hours=5, minutes=30))
    today = datetime.now(local).replace(hour=9, minute=0, second=0, microsecond=0)
    for company, offset in [(1, 1), (3, -1), (11, 0)]:
        due = (today + timedelta(days=offset)).astimezone(timezone.utc).isoformat()
        log_outreach_call(company_id=company, disposition="INTERESTED", follow_up_at=due,
                          feedback_notes="Workflow test on isolated database")
    client = TestClient(app)
    params = {"outreach": "FOLLOW_UP", "tz": "+05:30", "page_size": 10}
    response = client.get("/prospects", params=params)
    assert response.status_code == 200
    assert [c["company_id"] for c in response.context["company_groups"]] == [3, 11, 1]
    assert response.context["follow_up_counts"] == {"all": 3, "today": 1, "overdue": 1, "upcoming": 1}
    for window, company in [("today", 11), ("overdue", 3), ("upcoming", 1)]:
        response = client.get("/prospects", params={**params, "follow_up": window})
        assert [c["company_id"] for c in response.context["company_groups"]] == [company]
        card = response.context["company_groups"][0]
        assert card["last_call_outcome"] == "INTERESTED"
        assert card["last_feedback_notes"] == "Workflow test on isolated database"
    narrowed = client.get("/prospects", params={**params, "q": "Beasley"})
    assert [c["company_id"] for c in narrowed.context["company_groups"]] == [1]
    for offset, company in enumerate([16, 6, 7, 8, 10, 12, 13, 14, 15], start=2):
        log_outreach_call(company_id=company, disposition="CALL_BACK",
                          follow_up_at=(today + timedelta(days=offset)).isoformat())
    first_page = client.get("/prospects", params=params).context["company_groups"]
    second_page = client.get("/prospects", params={**params, "page": 2}).context["company_groups"]
    assert len(first_page) == 10
    assert [c["company_id"] for c in first_page[:3]] == [3, 11, 1]
    assert [c["company_id"] for c in second_page] == [14, 15]
    client.post("/api/outreach/1/clear", json={"action": "clear_status"})
    group = next(c for c in client.get("/api/companies").json() if c["company_id"] == 1)
    assert group["outreach_status"] == "UNCONTACTED"
    assert group["last_call_outcome"] == "INTERESTED"


def test_browser_workflow_logic():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / "src/frontend/static/js/workflow.js").read_text(encoding="utf-8")
    modal = (root / "src/frontend/templates/partials/log_call_modal.html").read_text(encoding="utf-8")
    modal_script = modal.split("<script>", 1)[1].split("</script>", 1)[0]
    script = r'''
const assert = require('node:assert/strict');
const vm = require('node:vm');
const values = new Map(), listeners = {}, events = [];
let focused = '', copied = '', fetched = '';
const context = {
  window: {location: {origin:'http://localhost', pathname:'/prospects'}, URL,
    addEventListener: (name, handler) => listeners[name] = handler,
    dispatchEvent: e => events.push(e)},
  sessionStorage: {getItem: key => values.get(key) || null, setItem: (key, value) => values.set(key, value)},
  navigator: {clipboard: {writeText: async value => copied = value}},
  CustomEvent: class {constructor(type, options={}) {this.type=type; this.detail=options.detail;}},
  document: {activeElement:null, getElementById: id => ({focus: () => focused=id,
    textContent: '{"INTERESTED":"Interested"}'})},
  URLSearchParams, Date, setTimeout: () => {}, clearTimeout: () => {},
  fetch: async url => {fetched=url; return {ok:true, text:async()=>'', json:async()=>({data:{disposition:'INTERESTED', follow_up_at:null}})};},
  DOMParser: class {parseFromString() {return {getElementById:()=>({textContent:JSON.stringify([
    {company_id:3, primary_facility_id:30, operating_brand:'Third'}])})};}}
};
vm.createContext(context);
vm.runInContext(WORKFLOW, context);
vm.runInContext(MODAL, context);
(async () => {
  const workflow = context.window.freightWorkflow;
  context.freightWorkflow = workflow;
  for(let id=1; id<=6; id++) workflow.remember({facilityId:id, name:'Company '+id});
  workflow.remember({facilityId:3, name:'Third'});
  assert.deepEqual(Array.from(workflow.recentProfiles(), x=>x.facilityId), [3,6,5,4,2]);
  await workflow.copy('555-0100','Phone');
  assert.equal(copied,'555-0100');
  assert.equal(events.at(-1).detail,'Phone copied');
  context.navigator.clipboard.writeText = async () => {throw new Error('denied');};
  await workflow.copy('a@example.com','Email');
  assert.match(events.at(-1).detail,/Could not copy/);
  const state={url:'/prospects?q=steel', mode:'COMPANIES',page:1,totalPages:2,sort:'name_asc',anchorId:'old',sequence:[
    {companyId:1,facilityId:10,name:'First'}, {companyId:2,facilityId:20,name:'Second'}]};
  workflow.store('fp_directory_position',state);
  let neighbors=await workflow.neighbors({facilityId:10,companyId:1,returnTo:state.url});
  assert.equal(neighbors.previous,null);
  assert.ok(neighbors.next.href.includes('/prospects/20'));
  neighbors=await workflow.neighbors({facilityId:20,companyId:2,returnTo:state.url});
  assert.equal(neighbors.previous.name,'First');
  assert.equal(neighbors.next.name,'Third');
  assert.equal(neighbors.next.context.anchorId,null);
  assert.match(fetched,/q=steel.*page=2/);
  const modal=context.logCallModalComponent();
  modal.$nextTick = callback=>callback();
  modal.init();
  listeners['open-log-call']({detail:{companyId:1,companyName:'First'}});
  assert.equal(modal.hasUnsavedChanges(),false);
  modal.feedbackNotes='Important unsaved notes';
  modal.closeModal();
  assert.equal(modal.open,true);
  assert.equal(modal.confirmDiscard,true);
  modal.keepEditing();
  assert.equal(modal.feedbackNotes,'Important unsaved notes');
  assert.equal(focused,'call-contact-name');
  let prevented=false;
  listeners.beforeunload({preventDefault:()=>prevented=true});
  assert.equal(prevented,true);
  modal.closeModal(true);
  assert.equal(modal.open,false);
  listeners['open-log-call']({detail:{companyId:1,companyName:'First'}});
  modal.disposition='INTERESTED';
  await modal.submitCall();
  assert.equal(modal.saved,true);
  assert.equal(modal.hasUnsavedChanges(),false);
  assert.equal(workflow.read('fp_saved_call'),'Saved — First: Interested. No follow-up scheduled.');
  assert.equal(events.at(-1).type,'outreach-logged');
})().catch(error=>{console.error(error);process.exitCode=1;});
'''.replace("WORKFLOW", json.dumps(workflow)).replace("MODAL", json.dumps(modal_script))
    node = shutil.which("node") or r"C:\Program Files\nodejs\node.exe"
    result = subprocess.run([node, "-"], input=script, encoding="utf-8", capture_output=True)
    assert result.returncode == 0, result.stderr

import assert from 'node:assert/strict';
import fs from 'node:fs';
import {chromium} from 'playwright-core';
const assets=new URL('../src/v2lens/resources/',import.meta.url);
const html=fs.readFileSync(new URL('panel.html',assets),'utf8').replace('<!-- JSON_EDITOR_BUNDLE -->',()=>'<script>'+fs.readFileSync(new URL('json-editor.js',assets),'utf8').replace(/<\/script/gi,'<\\/script')+'</script>');
const browser=await chromium.launch({channel:'msedge',headless:true});
try {
  const page=await browser.newPage({viewport:{width:980,height:720}});
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.evaluate(()=>{
    window.saved=[];window.folds={tun:{folds:[]},standard:{folds:[]}};window.closedCount=0;window.prompts=0;
    window.confirm=()=>{window.prompts++;return false;};
    window.pywebview={api:{
      get_preferences:async()=>({}),snapshot:async()=>({records:[]}),
      get_template:async mode=>({ok:true,text:mode==='tun'?'{"inbounds":[{"tag":"tun","protocol":"tun"}],"routing":{"rules":[]}}':'',revision:mode+'1',enabled:true}),
      get_editor_state:async mode=>window.folds[mode],
      set_editor_state:async(value,mode)=>{window.folds[mode]=value;return true;},
      save_template:async(text,revision,auto_reload,mode)=>{
        window.saved.push({text,revision,auto_reload,mode});
        await new Promise(resolve=>{window.finishSave=resolve;});
        return window.conflict?{ok:false,conflict:true,error:'Changed elsewhere'}:{ok:true,revision:mode+'2',enabled:true,applies_when:mode};
      },
      close:()=>{window.closedCount++;},begin_resize:async edge=>{window.edge=edge;},
      maximize:async()=>true
    }};
  });
  await page.setContent(html);
  await page.evaluate(()=>window.dispatchEvent(new Event('pywebviewready')));
  await page.getByRole('tab',{name:'Template',exact:true}).click();
  await page.waitForFunction(()=>templateLoaded);
  await page.getByRole('button',{name:'Format',exact:true}).click();
  const tunDraft=await page.evaluate(()=>getTemplateEditor().getValue());
  await page.locator('.cm-foldGutter .cm-gutterElement').filter({hasText:'⌄'}).first().click();
  await page.waitForFunction(()=>window.folds.tun.folds.length===1);
  await page.getByRole('button',{name:'Without TUN',exact:true}).click();
  await page.waitForFunction(()=>templateLoaded&&!templateBusy);
  assert.equal(await page.evaluate(()=>getTemplateEditor().getValue()),'','An empty standard template stays empty');
  assert.equal(await page.locator('#template-status').textContent(),'','An empty template has no idle status text');
  assert.equal(await page.evaluate(()=>hasTemplateDrafts()),true,'An inactive TUN draft is still unsaved');
  await page.locator('#close').click();
  assert.equal(await page.evaluate(()=>window.prompts),1,'Closing warns about an inactive draft');
  assert.equal(await page.evaluate(()=>window.closedCount),0);
  const standard='{"inbounds":[{"tag":"socks","protocol":"socks","port":1080}]}';
  await page.locator('.cm-content').focus();
  await page.keyboard.insertText(standard);
  await page.getByRole('button',{name:'TUN',exact:true}).click();
  assert.equal(await page.evaluate(()=>getTemplateEditor().getValue()),tunDraft,'TUN draft is restored');
  assert.equal(await page.locator('.cm-foldPlaceholder').count(),1,'TUN folds survive switching');
  await page.getByRole('button',{name:'Expand all',exact:true}).click();
  await page.locator('.cm-content').focus();
  await page.keyboard.press('Control+z');
  assert.equal(await page.evaluate(()=>getTemplateEditor().getValue()),'{"inbounds":[{"tag":"tun","protocol":"tun"}],"routing":{"rules":[]}}','TUN undo history is independent');
  await page.getByRole('button',{name:'Without TUN',exact:true}).click();
  assert.equal(await page.evaluate(()=>getTemplateEditor().getValue()),standard,'Standard draft is restored');
  await page.locator('#save-template').click();
  await page.waitForFunction(()=>window.saved.length===1);
  assert.equal(await page.getByRole('button',{name:'TUN',exact:true}).isDisabled(),true,'Modes cannot switch during validation');
  assert.deepEqual(await page.evaluate(()=>window.saved[0]),{text:standard,revision:'standard1',auto_reload:false,mode:'standard'});
  await page.evaluate(()=>window.finishSave());
  await page.waitForFunction(()=>!templateBusy);
  assert.match(await page.locator('#template-status').textContent(),/Applies when TUN is off/);
  assert.equal(await page.evaluate(()=>hasTemplateDrafts()),false,'Saved and undone drafts do not prompt');
  await page.locator('.cm-content').focus();
  await page.keyboard.press('Control+End');
  await page.keyboard.insertText(' ');
  await page.evaluate(()=>{window.conflict=true;});
  await page.locator('#save-template').click();
  await page.waitForFunction(()=>window.saved.length===2);
  await page.evaluate(()=>window.finishSave());
  await page.waitForFunction(()=>!templateBusy);
  await page.getByRole('button',{name:'TUN',exact:true}).click();
  await page.getByRole('button',{name:'Without TUN',exact:true}).click();
  assert.equal(await page.locator('#reload-template').isVisible(),true,'Conflict state belongs to its mode');
  assert.equal(await page.evaluate(()=>getTemplateEditor().getValue()),standard+' ','Conflict preserves unsaved text');
  assert.deepEqual(await page.evaluate(()=>window.folds.standard.folds),[],'Standard folds are separate');
  await page.locator('[data-resize="bottom-right"]').dispatchEvent('pointerdown',{button:0});
  assert.equal(await page.evaluate(()=>window.edge),'bottom-right');
  await page.locator('#maximize').click();
  await page.waitForFunction(()=>document.body.classList.contains('maximized'));
  assert.equal(await page.locator('[data-resize="bottom-right"]').isVisible(),false);
  assert.deepEqual(errors,[]);
  console.log('PASS: independent template drafts, undo, folds, saves, conflicts, close guard and resize controls');
} finally {await browser.close();}

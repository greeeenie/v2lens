import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright-core';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const assets=path.join(root,'src/v2lens/resources');
const html=fs.readFileSync(path.join(assets,'panel.html'),'utf8');
const script=html.match(/<script>([\s\S]*?)<\/script>/)[1];
const stub={addEventListener(){},checked:false};
const context=vm.createContext({performance:{now:()=>1000},document:{getElementById:()=>stub,querySelectorAll:()=>[],addEventListener(){}},window:{addEventListener(){}}});
vm.runInContext(script,context);
const record=(pid,inbound,down=100)=>({app:'Demo.exe',pid,inbound,protocol:'TCP',outbound:'proxy',destination:'example.com',port:443,
  source:'172.18.0.1',local_port:50000+pid,time:Date.now()/1000,traffic:{sent:10,received:100,up_rate:10,down_rate:down}});
context.input=[record(1,'tun'),record(2,'tun'),record(1,'socks',200)];
const run=code=>vm.runInContext(code,context);
assert.equal(run("buildGroups(input,'','all',false,false).length"),3,'Different gateways do not merge');
run("app=buildGroups(input,'','all',false,true)[0]");
assert.equal(run('app.record.traffic.down_rate'),400,'Each gateway contributes traffic once');
assert.equal(run('app.record.summary.inbounds.join(",")'),'socks,tun');
assert.equal(run('flattenGroups([app]).length'),1);
run('expandedApps.add(app.key)');
assert.equal(run('flattenGroups([app]).length'),4,'App expands straight into three connections');
assert.equal(run('flattenGroups([app]).filter(g=>g.depth===1).length'),3);
assert.equal(run('flattenGroups([app]).filter(g=>g.depth>1 || g.depth===1 && g.members).length'),0,'No intermediate PID groups');
assert.equal(run('flattenGroups([app]).filter(g=>g.depth===1).map(g=>g.record.pid).join(",")'),'1,1,2');
assert.equal(run("buildGroups(input,'','all',false,false).sort((a,b)=>compareGroups(a,b,'gateway','asc'))[0].record.inbound"),'socks');
assert.equal(run("buildGroups(input,'','all',false,false).sort((a,b)=>compareGroups(a,b,'gateway','desc'))[0].record.inbound"),'tun');
assert.equal(run("gatewayLabel('other-inbound')"),'other-inbound','Custom tags remain explicit');

const browser=await chromium.launch({channel:'msedge',headless:true});
try {
  const page=await browser.newPage({viewport:{width:980,height:720},reducedMotion:'reduce'});
  await page.setContent(html);
  await page.evaluate(input=>{records=input;receivedSnapshot=true;document.getElementById('group-app').checked=true;render();},context.input);
  await page.getByRole('button',{name:'Expand Demo.exe',exact:true}).click();
  assert.equal(await page.locator('.row').count(),4);
  assert.equal(await page.locator('.connection-row .expander:not([hidden])').count(),0);
  assert.equal(await page.locator('.process-row').count(),0);
  assert.deepEqual(await page.locator('.connection-row .gateway').allTextContents(),['SOCKS','TUN','TUN']);
  assert.deepEqual(await page.locator('.connection-row .pid').allTextContents(),['1','1','2']);
  assert.ok((await page.locator('.connection-row .app-name').allTextContents()).every(name=>name.startsWith('172.18.0.1:')));
  assert.ok((await page.locator('.row').evaluateAll(rows=>rows.map(r=>r.children.length))).every(count=>count===7),'Headers and rows have seven columns');
  assert.deepEqual(await page.locator('.row').first().evaluate(row=>[...row.children].map(cell=>cell.className)),['application','pid','protocol','target','gateway','route proxy','traffic'],'Gateway and route are adjacent; traffic is last');
  for(const width of [690,800,920,980,1280]) {
    await page.setViewportSize({width,height:720});
    assert.ok(await page.locator('.row').first().evaluate(row=>row.scrollWidth<=row.clientWidth+1),'Columns fit at '+width+'px');
    const aligned=await page.evaluate(()=>{
      const headers=[...document.querySelector('.columns').children],cells=[...document.querySelector('.row').children];
      return headers.every((header,i)=>Math.abs(header.getBoundingClientRect().left-cells[i].getBoundingClientRect().left)<1);
    });
    assert.ok(aligned,'Column headings align with their cells at '+width+'px');
  }
  await page.getByRole('button',{name:'Gateway',exact:true}).click();
  assert.equal(await page.locator('[data-sort-cell="gateway"]').getAttribute('aria-sort'),'ascending');
  await page.getByRole('button',{name:'Collapse Demo.exe',exact:true}).click();
  assert.equal(await page.locator('.row').count(),1);
  await page.setViewportSize({width:690,height:500});
  assert.ok(await page.locator('.row').evaluate(row=>row.scrollWidth<=row.clientWidth+1),'Columns fit the minimum window width');
  assert.equal(await page.locator('.row').evaluateAll(rows=>rows.flatMap(row=>row.getAnimations()).length),0,'Reduced motion disables row animation');
  const motion=await browser.newPage({viewport:{width:980,height:720},reducedMotion:'no-preference'});
  await motion.setContent(html);
  const moves=await motion.evaluate(input=>{
    records=[{...input[0],app:'First.exe',time:2},{...input[1],app:'Second.exe',time:1}];
    sortField='time';sortDirection='desc';render();
    records[1].time=3;render(true);
    return [...document.querySelectorAll('.row')].map(row=>row.getAnimations().map(animation=>({duration:animation.effect.getTiming().duration,easing:animation.effect.getTiming().easing,frames:animation.effect.getKeyframes()})));
  },context.input);
  assert.ok(moves.every(animations=>animations.length===1&&animations[0].duration===150),'Both displaced rows animate for 150 ms');
  assert.ok(moves[0][0].frames[0].transform.startsWith('translateY(44'),'Promoted row starts at its previous lower position');
  assert.ok(moves[1][0].frames[0].transform.startsWith('translateY(-44'),'Displaced row starts at its previous higher position');
  assert.ok(moves.every(([animation])=>!Object.hasOwn(animation.frames[0],'opacity')),'Reordering moves existing rows without fading them');
  assert.ok(moves.every(([animation])=>animation.easing==='ease-in-out'),'Rows accelerate and decelerate smoothly together');
  assert.equal(moves[0][0].frames[0].zIndex,'2','The rising row stays above its displaced neighbors');
  assert.equal(moves[1][0].frames[0].zIndex,'1','Displaced neighbors slide beneath the rising row');
  const visibleRise=await motion.evaluate(()=>{
    const [rising,displaced]=document.querySelectorAll('.row');
    for(const row of [rising,displaced])for(const animation of row.getAnimations()){animation.pause();animation.currentTime=75;}
    const rect=rising.getBoundingClientRect(),neighbor=displaced.getBoundingClientRect();
    return {visible:document.elementFromPoint(rect.left+20,rect.top+rect.height/2)?.closest('.row')===rising,overlap:Math.abs(rect.top-neighbor.top)<1};
  });
  assert.ok(visibleRise.overlap&&visibleRise.visible,'The rising row remains visible while crossing its displaced neighbor halfway through the animation');
  const interrupted=await motion.evaluate(()=>{
    records[0].time=4;render(true);
    return [...document.querySelectorAll('.row')].map(row=>row.getAnimations().length);
  });
  assert.ok(interrupted.every(count=>count<=1),'A new update replaces the previous movement instead of stacking animations');
  await motion.waitForTimeout(200);
  assert.equal(await motion.locator('.row').evaluateAll(rows=>rows.flatMap(row=>row.getAnimations()).length),0,'Movement finishes cleanly');
  const distant=await motion.evaluate(input=>{
    records=Array.from({length:50},(_,i)=>({...input[0],app:`App${i}.exe`,pid:100+i,time:50-i}));
    render();
    for(const row of document.querySelectorAll('.row'))for(const animation of row.getAnimations())animation.finish();
    const row=[...document.querySelectorAll('.row')].at(-1);
    const original=row.getBoundingClientRect().top,bottom=document.querySelector('.rows').getBoundingClientRect().bottom;
    records[49].time=100;render(true);
    const animation=row.getAnimations()[0],frame=animation.effect.getKeyframes()[0];
    animation.cancel();
    const rect=row.getBoundingClientRect();
    return {original,bottom,start:rect.top+Number(frame.transform.match(/translateY\(([-.\d]+)px\)/)[1]),height:rect.height,duration:animation.effect.getTiming().duration};
  },context.input);
  assert.ok(distant.original>distant.bottom+1000,'Test promotes a row from far below the visible table');
  assert.ok(Math.abs(distant.start-(distant.bottom-distant.height))<1,'Offscreen row starts at the last visible row instead of its distant position');
  assert.equal(distant.duration,150,'Clamping the starting position preserves the fast duration');
  await motion.close();
} finally {await browser.close();}
console.log('PASS: flat application details, visible PIDs, separate/sortable gateways and traffic deduplication');

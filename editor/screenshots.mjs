// Render the real interface with synthetic data, never a user's network history.
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright-core';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
fs.mkdirSync(path.join(root,'docs'),{recursive:true});
const html=fs.readFileSync(path.join(root,'panel.html'),'utf8').replace('<!-- JSON_EDITOR_BUNDLE -->',()=>'<script>'+fs.readFileSync(path.join(root,'json-editor.js'),'utf8').replace(/<\/script/gi,'<\\/script')+'</script>');
const browser=await chromium.launch({channel:'msedge',headless:true});
try {
  const page=await browser.newPage({viewport:{width:1080,height:640},reducedMotion:'reduce'});
  await page.evaluate(()=>{
    const sample=JSON.stringify({inbounds:[{tag:'tun',protocol:'tun'}],routing:{rules:[
      {inboundTag:['tun'],process:['Discord.exe','Code.exe'],outboundTag:'proxy'},
      {inboundTag:['tun'],outboundTag:'direct'}]}},null,2);
    const rows=[
      ['Code.exe',3100,'TCP','github.com',443,'proxy',48000,1200],
      ['Discord.exe',4200,'TCP','gateway.discord.gg',443,'proxy',8200,1400],
      ['Discord.exe',4200,'UDP','voice.example.net',50000,'proxy',32000,28000],
      ['firefox.exe',5300,'TCP','example.com',443,'direct',245000,15000],
      ['firefox.exe',5300,'TCP','static.example.org',443,'direct',92000,4100],
      ['Steam.exe',6400,'TCP','store.steampowered.com',443,'direct',156000,8000],
      ['steamwebhelper.exe',6500,'TCP','cdn.example.net',443,'direct',65000,2200]
    ].map(([app,pid,protocol,destination,port,outbound,down,up],i)=>({
      app,pid,protocol,destination,port,outbound,inbound:'tun',id:i+1,time:Date.now()/1000-3-i,
      source:'172.18.0.1',local_port:50001+i,path:'C:\\Apps\\'+app,active:true,
      owner_evidence:'Synthetic screenshot data',traffic:{sent:up*10,received:down*10,up_rate:up,down_rate:down}
    }));
    window.pywebview={api:{
      get_preferences:async()=>({hide_unknown:true,group_by_app:false,sort_field:'app',sort_direction:'asc',auto_reload:true}),
      snapshot:async()=>({records:rows,updated:'12:00:00',traffic:{status:'running',started:Date.now()/1000-120}}),
      get_template:async()=>({ok:true,text:sample,revision:'demo',enabled:true}),
      get_editor_state:async()=>({folds:[]}),set_editor_state:async()=>true,
      set_auto_reload:async()=>true,set_group_by_app:async()=>true,set_hide_unknown:async()=>true
    }};
  });
  await page.setContent(html);
  await page.evaluate(()=>window.dispatchEvent(new Event('pywebviewready')));
  await page.locator('.row').first().waitFor();
  await page.screenshot({path:path.join(root,'docs/connections.png')});
  await page.getByRole('tab',{name:'Template',exact:true}).click();
  await page.locator('.cm-editor').waitFor();
  await page.waitForFunction(()=>document.querySelector('.cm-content')?.textContent.includes('Discord.exe'));
  await page.screenshot({path:path.join(root,'docs/template.png')});
} finally {await browser.close();}

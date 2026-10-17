import {build} from 'esbuild';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=path.dirname(fileURLToPath(import.meta.url));
await build({entryPoints:[path.join(root,'editor.js')],outfile:path.join(root,'../json-editor.js'),
  bundle:true,format:'iife',globalName:'XrayJsonEditor',platform:'browser',target:'es2020',minify:true,legalComments:'eof'});
const lock=JSON.parse(fs.readFileSync(path.join(root,'package-lock.json'),'utf8'));
const notices=[];
for(const [folder,details] of Object.entries(lock.packages)) {
  if(!folder.startsWith('node_modules/') || folder.includes('esbuild'))continue;
  const license=path.join(root,folder,'LICENSE');
  if(fs.existsSync(license))notices.push(`${folder.slice(13)} ${details.version}\n${fs.readFileSync(license,'utf8')}`);
}
fs.writeFileSync(path.join(root,'../json-editor.LICENSE.txt'),notices.join('\n\n----\n\n'));
console.log('Built offline JSON editor');

import {jsonLanguage} from '@codemirror/lang-json';

const isContainer=node=>node?.name==='Object' || node?.name==='Array';
const children=node=>{
  const result=[];
  for(let child=node.firstChild;child;child=child.nextSibling)
    if(node.name==='Object'?child.name==='Property':!['[',']',','].includes(child.name))result.push(child);
  return result;
};
const valueOf=node=>node.name==='Property'?node.lastChild:node;

// Paths survive changes in whitespace and avoid storing template contents in UI state.
export function jsonBlocks(text) {
  JSON.parse(text);
  const result=[];
  const visit=(node,path)=>{
    if(!isContainer(node))return;
    result.push({node,path});
    children(node).forEach((child,index)=>visit(valueOf(child),[...path,
      node.name==='Object'?JSON.parse(text.slice(child.firstChild.from,child.firstChild.to)):index]));
  };
  visit(jsonLanguage.parser.parse(text).topNode.firstChild,[]);
  return result;
}

export function valueInsertion(text,position) {
  const blocks=jsonBlocks(text);
  if(!blocks.length)throw new Error('Place the cursor inside an object or array.');
  // An opening line inserts at the start; a closing line inserts after that block in its parent.
  const block=[...blocks].reverse().find(({node})=>position>=node.from && position<node.lastChild.from) || blocks[0];
  const {node}=block,items=children(node);
  const index=items.findLastIndex(item=>item.from<position);
  const after=items[index],next=items[index+1];
  const base=text.slice(text.lastIndexOf('\n',node.from-1)+1,node.from).match(/^\s*/)[0];
  const indent=base+'  ';
  let entry='null',offset=0,length=4;
  if(node.name==='Object') {
    const names=new Set(items.map(item=>JSON.parse(text.slice(item.firstChild.from,item.firstChild.to))));
    let name='key',suffix=2;while(names.has(name))name='key'+suffix++;
    entry=JSON.stringify(name)+': null';offset=1;length=name.length;
  } else {
    const neighbor=valueOf(after || next || node);
    const defaults={String:['""',1,0],Object:['{}',1,0],Array:['[]',1,0],Number:['0',0,1],True:['false',0,5],False:['false',0,5]};
    // An empty array has no element type to infer.
    if(items.length && defaults[neighbor.name])[entry,offset,length]=defaults[neighbor.name];
  }
  const from=after?after.to:node.firstChild.to,to=next?next.from:node.lastChild.from;
  const prefix=(after?',':'')+'\n'+indent;
  const insert=prefix+entry+(next?',\n'+indent:'\n'+base);
  return {from,to,insert,anchor:from+prefix.length+offset,head:from+prefix.length+offset+length};
}

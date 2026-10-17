import {Compartment,EditorState,Transaction} from '@codemirror/state';
import {Decoration,EditorView,ViewPlugin,WidgetType,drawSelection,highlightActiveLine,highlightActiveLineGutter,keymap,lineNumbers} from '@codemirror/view';
import {defaultKeymap,history,historyKeymap,indentWithTab} from '@codemirror/commands';
import {HighlightStyle,bracketMatching,foldEffect,foldGutter,foldInside,foldKeymap,foldedRanges,indentOnInput,indentUnit,syntaxHighlighting,unfoldAll,unfoldEffect} from '@codemirror/language';
import {json,jsonParseLinter} from '@codemirror/lang-json';
import {linter} from '@codemirror/lint';
import {searchKeymap} from '@codemirror/search';
import {closeBrackets,closeBracketsKeymap} from '@codemirror/autocomplete';
import {tags} from '@lezer/highlight';
import {formatJson} from './format.js';
import {jsonBlocks,valueInsertion} from './structure.js';

class AddValueButton extends WidgetType {
  constructor(position,onAdd){super();this.position=position;this.onAdd=onAdd;}
  eq(other){return this.position===other.position && this.onAdd===other.onAdd;}
  toDOM(){
    const button=document.createElement('button');button.textContent='+';button.type='button';
    button.className='cm-addValue';button.contentEditable='false';
    button.title='Add value after line';button.setAttribute('aria-label',button.title);
    button.onmousedown=event=>event.preventDefault();
    button.onclick=event=>{event.preventDefault();event.stopPropagation();this.onAdd(this.position);};
    return button;
  }
}

const colors=HighlightStyle.define([
  {tag:tags.propertyName,color:'#bdb0e4'},
  {tag:tags.string,color:'#a4c7b0'},
  {tag:tags.number,color:'#d4ba8d'},
  {tag:[tags.bool,tags.null,tags.keyword],color:'#c3a7dc'},
  {tag:tags.punctuation,color:'#929ba8'},
  {tag:tags.invalid,color:'#e5a2a0'}
]);
const theme=EditorView.theme({
  '&':{height:'100%',color:'#c2c9d4',backgroundColor:'#15181b',fontSize:'12px'},
  '&.cm-focused':{outline:'none'},
  '.cm-scroller':{fontFamily:'"Cascadia Code",Consolas,monospace',lineHeight:'1.65',overflow:'auto'},
  '.cm-content':{padding:'14px 0',caretColor:'#e8e9ec'},
  '.cm-line':{padding:'0 15px 0 8px'},
  '.cm-gutters':{backgroundColor:'#15181b',color:'#59616d',border:'none',padding:'0 5px 0 8px'},
  '.cm-lineNumbers .cm-gutterElement':{minWidth:'29px',paddingRight:'6px'},
  '.cm-activeLineGutter':{backgroundColor:'transparent',color:'#aab2c0'},
  '.cm-activeLine':{backgroundColor:'#ffffff03'},
  '.cm-foldGutter .cm-gutterElement':{cursor:'pointer',color:'#858391',padding:'0 3px'},
  '.cm-addValue':{display:'inline-block',width:'18px',height:'18px',marginLeft:'8px',padding:'0',border:'0',borderRadius:'4px',background:'transparent',color:'#858391',font:'15px/18px "Segoe UI",sans-serif',verticalAlign:'middle',cursor:'pointer'},
  '.cm-addValue:hover,.cm-addValue:focus-visible':{background:'#b2aafa19',color:'#ded7ee'},
  '.cm-foldPlaceholder':{backgroundColor:'#252831',border:'none',borderRadius:'4px',color:'#a89abd',padding:'0 5px'},
  '&.cm-focused .cm-selectionBackground,.cm-selectionBackground,::selection':{backgroundColor:'#63577f55 !important'},
  '.cm-cursor,.cm-dropCursor':{borderLeftColor:'#d8d0eb'},
  '.cm-matchingBracket':{backgroundColor:'#b2aafa19',outline:'1px solid #8e86d14d',borderRadius:'2px'},
  '.cm-tooltip':{border:'1px solid #343944',backgroundColor:'#20242a',color:'#d1d6df',borderRadius:'6px'},
  '.cm-panels':{backgroundColor:'#191c20',color:'#aab2bd',borderColor:'#282c31'},
  '.cm-search':{fontFamily:'"Segoe UI",sans-serif',fontSize:'11px',padding:'8px'},
  '.cm-search input,.cm-search button':{font:'inherit',border:'1px solid #343944',borderRadius:'4px',backgroundColor:'#24282e',color:'#d1d6df'},
  '.cm-diagnostic':{padding:'7px 10px',fontSize:'11px'},
  '.cm-diagnostic-error':{borderLeftColor:'#d6a09c'}
},{dark:true});

export function create(parent,{onChange,onSave,onError,onFoldsChange=()=>{}}) {
  const mode=new Compartment();
  let readOnly=true,view,restoring=false,lastFolds='[]';
  const foldPaths=()=>{
    if(!view.state.doc.toString().trim())return [];
    const blocks=jsonBlocks(view.state.doc.toString()),paths=[];
    foldedRanges(view.state).between(0,view.state.doc.length,(from,to)=>{
      const block=blocks.find(({node})=>{const range=foldInside(node);return range?.from===from && range.to===to;});
      if(block)paths.push(block.path);
    });
    return paths;
  };
  const rememberFolds=()=>{
    if(restoring)return;
    try {
      const paths=foldPaths(),serialized=JSON.stringify(paths);
      if(serialized!==lastFolds){lastFolds=serialized;onFoldsChange(paths);}
    }catch{} // Keep the last valid state while a JSON edit is incomplete.
  };
  const restoreFolds=paths=>{
    if(!view.state.doc.toString().trim()){unfoldAll(view);return;}
    const wanted=new Set(paths.map(path=>JSON.stringify(path)));
    const effects=jsonBlocks(view.state.doc.toString()).filter(block=>wanted.has(JSON.stringify(block.path)))
      .map(({node})=>foldInside(node)).filter(range=>range && range.from<range.to).map(range=>foldEffect.of(range));
    unfoldAll(view);
    if(effects.length)view.dispatch({effects});
  };
  const format=()=>{
    if(readOnly)return false;
    try {
      const text=view.state.doc.toString(),formatted=formatJson(text);
      if(formatted!==text){
        const paths=foldPaths();restoring=true;
        try {
          view.dispatch({changes:{from:0,to:text.length,insert:formatted},
            selection:{anchor:Math.min(view.state.selection.main.head,formatted.length)},
            annotations:Transaction.userEvent.of('input.format')});
          restoreFolds(paths);
        }finally{restoring=false;}
        rememberFolds();
      }
      return true;
    }catch(error){onError(error.message);return false;}
  };
  const addValue=position=>{
    if(readOnly)return false;
    try {
      const {from,to,insert,anchor,head}=valueInsertion(view.state.doc.toString(),position);
      view.dispatch({changes:{from,to,insert},selection:{anchor,head},scrollIntoView:true,
        annotations:Transaction.userEvent.of('input.addValue')});view.focus();return true;
    }catch(error){onError(error.message);return false;}
  };
  const addButton=ViewPlugin.fromClass(class {
    constructor(view){this.decorations=this.build(view);}
    update(update){
      if(update.docChanged || update.selectionSet || update.transactions.some(tr=>tr.reconfigured))
        this.decorations=this.build(update.view);
    }
    build(view){
      if(view.state.readOnly)return Decoration.none;
      const position=view.state.doc.lineAt(view.state.selection.main.head).to;
      return Decoration.set([Decoration.widget({widget:new AddValueButton(position,addValue),side:1}).range(position)]);
    }
  },{decorations:plugin=>plugin.decorations});
  const extensions=()=>[
    lineNumbers(),foldGutter(),addButton,highlightActiveLineGutter(),history(),drawSelection(),
    json(),syntaxHighlighting(colors),indentOnInput(),indentUnit.of('  '),bracketMatching(),
    closeBrackets(),highlightActiveLine(),linter(jsonParseLinter(),{delay:350}),theme,
    mode.of([EditorState.readOnly.of(readOnly),EditorView.editable.of(!readOnly)]),
    EditorView.contentAttributes.of({'aria-label':'Full Xray template JSON','spellcheck':'false'}),
    keymap.of([
      {key:'Mod-s',preventDefault:true,run:()=>{onSave();return true;}},
      {key:'Mod-Shift-f',preventDefault:true,run:format},
      {key:'Alt-Shift-f',preventDefault:true,run:format},
      indentWithTab,...closeBracketsKeymap,...defaultKeymap,...historyKeymap,...foldKeymap,...searchKeymap
    ]),
    EditorView.updateListener.of(update=>{
      if(update.docChanged)onChange();
      if(update.docChanged || update.transactions.some(tr=>tr.effects.some(effect=>effect.is(foldEffect) || effect.is(unfoldEffect))))rememberFolds();
    })
  ];
  view=new EditorView({state:EditorState.create({doc:'',extensions:extensions()}),parent});
  return {
    getValue:()=>view.state.doc.toString(),
    captureState:()=>view.state,
    restoreState:state=>{
      restoring=true;
      try{view.setState(state);readOnly=state.readOnly;try{lastFolds=JSON.stringify(foldPaths());}catch{lastFolds='[]';}}
      finally{restoring=false;}
    },
    setValue:(text,{folds=[]}={})=>{
      restoring=true;
      try {
        view.setState(EditorState.create({doc:text,extensions:extensions()}));
        restoreFolds(folds);lastFolds=JSON.stringify(foldPaths());
      }finally{restoring=false;}
    },
    setReadOnly:value=>{readOnly=value;view.dispatch({effects:mode.reconfigure([EditorState.readOnly.of(value),EditorView.editable.of(!value)])});},
    focus:()=>view.focus(),
    refresh:()=>view.requestMeasure(),
    format,
    expandAll:()=>unfoldAll(view)
  };
}

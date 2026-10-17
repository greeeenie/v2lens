// Keep original string and number literals intact while formatting valid JSON.
export function formatJson(text) {
  JSON.parse(text);
  const tokens=text.match(/"(?:[^"\\]|\\.)*"|-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?|true|false|null|[{}\[\],:]/g);
  let result='',depth=0;
  const newline=()=>{result+='\n'+'  '.repeat(depth);};
  for(let i=0;i<tokens.length;i++) {
    const token=tokens[i];
    if(token==='{' || token==='[') {
      result+=token;depth++;
      if(tokens[i+1]!=='}' && tokens[i+1]!==']')newline();
    } else if(token==='}' || token===']') {
      depth--;
      if(tokens[i-1]!=='{' && tokens[i-1]!=='[')newline();
      result+=token;
    } else if(token===',') {result+=',';newline();}
    else if(token===':')result+=': ';
    else result+=token;
  }
  return result+'\n';
}

const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const html = fs.readFileSync(path.join(__dirname,'../src/readscout/web/index.html'),'utf8');
const script = html.split('<script>')[1].split('</script>')[0].replace("show('__VIEW__');load();",'');

async function run(action, failure){
  const elements = new Map();
  let loads = 0;
  const context = {
    document:{getElementById(id){if(!elements.has(id))elements.set(id,{style:{},addEventListener(){}});return elements.get(id);}},
    fetch:async()=>{
      if(failure==='network')throw Error('offline');
      return {ok:!failure,status:failure?500:200,json:async()=>({error:'audit rejection',message:'Done.'})};
    },
    setTimeout:()=>1,clearTimeout(){},confirm:()=>true,window:{}, onLoad:()=>{loads++}
  };
  vm.createContext(context);vm.runInContext(script,context);
  vm.runInContext(`load=onLoad; S={recommended:{fast:{model:'fast'},quality:{model:'quality'}},chosen:{vram_gb:8,ram_gb:32}}; ${action}`,context);
  await new Promise(resolve=>setImmediate(resolve));
  const message=elements.get('msg').textContent;
  if(failure){assert.match(message,/^Error:/);assert.equal(loads,0)}
  else assert.doesNotMatch(message,/^Error:/);
  return message;
}
(async()=>{
  for(const action of ['useModels()',"pull('fast')","agent('codex','install')",'applyEnv()']){
    await run(action,'http');await run(action,'network');await run(action,false);
  }
  assert.equal(await run('useModels()',false),'Saved.');
  console.log('12 setup action scenarios and success toast passed');
})().catch(error=>{console.error(error);process.exitCode=1});

import {mkdtemp,readFile,writeFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
const root=resolve(fileURLToPath(new URL('../..',import.meta.url)));
const {build}=await import(pathToFileURL(join(root,'frontend/node_modules/vite/dist/node/index.js')));
const temp=await mkdtemp(join(tmpdir(),'wp2c-fixtures-'));
try{
 await build({configFile:false,root:join(root,'frontend'),build:{ssr:'src/fixtures.ts',outDir:temp,emptyOutDir:true,rollupOptions:{output:{entryFileNames:'fixture.mjs'}}}});
 const f=await import(pathToFileURL(join(temp,'fixture.mjs')));
 const content=JSON.stringify({snapshot:f.snapshot(),settings:f.defaults,actual:f.actual,original:f.original,latest:f.latest,intervals:f.intervals,cycleEnergy:f.cycleEnergy,timeline:f.timeline,metrics:f.metrics},null,2)+'\n';
 const target=join(root,'packages/ha_native/fixture.json');
 if(process.argv.includes('--check')){if(await readFile(target,'utf8')!==content)throw Error('Synthetic fixture drift');}
 else await writeFile(target,content);
 console.log('Synthetic-only native fixtures verified');
}finally{await rm(temp,{recursive:true,force:true});}

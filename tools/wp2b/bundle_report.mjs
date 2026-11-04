import {readdir,readFile} from 'node:fs/promises';
import {gzipSync} from 'node:zlib';
import {createHash} from 'node:crypto';
const files=await readdir(new URL('../../frontend/dist/assets/',import.meta.url));
const result=[];
for(const name of files){const bytes=await readFile(new URL('../../frontend/dist/assets/'+name,import.meta.url));result.push({name,bytes:bytes.length,gzip_bytes:gzipSync(bytes).length,sha256:createHash('sha256').update(bytes).digest('hex')});}
console.log(JSON.stringify({scope:'synthetic build only; no target-host claim',node:process.version,files:result},null,2));

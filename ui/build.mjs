import {build} from 'esbuild';
import {mkdir, writeFile} from 'node:fs/promises';
const result=await build({entryPoints:['src/main.tsx'],bundle:true,write:false,format:'esm',target:'es2022',minify:true});
const js=result.outputFiles[0].text.replace(/<\/script/gi,'<\\/script');
const html=`<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Research Slide Agent</title><body><div id="root"></div><script type="module">${js}</script></body></html>`;
await mkdir('../src/research_slide_agent/static',{recursive:true});
await writeFile('../src/research_slide_agent/static/viewer.html',html);

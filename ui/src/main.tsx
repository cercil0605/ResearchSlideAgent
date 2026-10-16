import React, {useEffect, useState} from 'react';
import {createRoot} from 'react-dom/client';
import {App} from '@modelcontextprotocol/ext-apps';

type Preview = {job:{id:string;state:string;attempts:number;error:string|null};images:{page:number;url:string}[];download_url:string|null};
const bridge = new App({name:'Research Slide Agent',version:'0.1.0'},{});
let receive: (data:Preview)=>void = ()=>{};
let fail: (error:string)=>void = ()=>{};
bridge.ontoolresult = result => {if(result.structuredContent) receive(result.structuredContent as unknown as Preview)};
const connected=bridge.connect().catch(error=>fail(String(error)));

function Viewer(){
  const [data,setData]=useState<Preview|null>(null);
  const [page,setPage]=useState(0);
  const [error,setError]=useState('');
  const [busy,setBusy]=useState(false);
  const [message,setMessage]=useState('');
  receive=setData;
  fail=setError;
  async function call(name:string,args:Record<string,unknown>){
    await connected;
    const result=await bridge.callServerTool({name,arguments:args});
    if(result.isError) throw new Error(result.content.filter(x=>x.type==='text').map(x=>x.text).join('\n'));
    return result.structuredContent as unknown as Preview;
  }
  async function refresh(){
    if(!data) return;
    setBusy(true);
    try{setData(await call('get_preview',{job_id:data.job.id}));setError('')}catch(e){setError(String(e))}finally{setBusy(false)}
  }
  async function retry(){
    if(!data) return;
    setBusy(true);
    try{await call('retry_job',{job_id:data.job.id});await refresh()}catch(e){setError(String(e))}finally{setBusy(false)}
  }
  useEffect(()=>{
    if(!data || !['queued','running','validating'].includes(data.job.state)) return;
    const timer=setTimeout(()=>void refresh(),3000);
    return ()=>clearTimeout(timer);
  },[data]);
  async function revise(){
    if(!data || !message.trim()) return;
    try{
      await bridge.sendMessage({role:'user',content:[{type:'text',text:`Research Slide Agent: ジョブ ${data.job.id} の ${page+1} ページ目を修正してください。\n${message}`} ]});
      setMessage('');
    }catch(e){setError(String(e))}
  }
  const selected=data?.images[Math.min(page,Math.max(0,data.images.length-1))];
  return <main style={{fontFamily:'system-ui',color:'var(--color-text-primary,#182537)',padding:16}}>
    <h2>Research Slide Agent</h2>
    {error && <p role="alert">{error}</p>}
    {!data ? <p>スライドの情報を待っています。UIが利用できない場合は get_preview のURLをご利用ください。</p> : <>
      <p role="status">状態: {data.job.state} / 試行: {data.job.attempts}/3{data.job.error && ` / ${data.job.error}`}</p>
      <nav style={{display:'flex',gap:8,flexWrap:'wrap'}} aria-label="操作">
        <button disabled={busy} onClick={()=>void refresh()}>再読み込み</button>
        {data.job.state==='failed' && <button disabled={busy||data.job.attempts>=3} onClick={()=>void retry()}>再実行</button>}
        <button onClick={()=>void bridge.requestDisplayMode({mode:'fullscreen'}).catch(e=>setError(String(e)))}>拡大</button>
        {data.download_url && <button onClick={()=>void bridge.openLink({url:data.download_url!}).catch(e=>setError(String(e)))}>PPTXをダウンロード</button>}
      </nav>
      {selected && <>
        <div style={{display:'flex',gap:8,overflowX:'auto',margin:'12px 0'}} aria-label="スライド一覧">
          {data.images.map((image,i)=><button key={image.page} aria-pressed={page===i} onClick={()=>setPage(i)} style={{minWidth:100}}><img alt={`${image.page}ページ`} src={image.url} style={{width:100,display:'block'}}/>{image.page}</button>)}
        </div>
        <img src={selected.url} alt={`${selected.page}ページのプレビュー`} style={{width:'100%',maxHeight:'70vh',objectFit:'contain'}} onError={()=>setError('プレビューURLの期限が切れた場合は再読み込みしてください。')}/>
        <label style={{display:'block',marginTop:12}}>このページへの修正指示<textarea value={message} onChange={e=>setMessage(e.target.value)} style={{display:'block',width:'100%',minHeight:70}}/></label>
        <button disabled={!message.trim()} onClick={()=>void revise()}>チャットで修正を相談</button>
      </>}
    </>}
  </main>
}
createRoot(document.getElementById('root')!).render(<Viewer/>);

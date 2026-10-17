import {useEffect, useState} from 'react';
import {createRoot} from 'react-dom/client';
import {App} from '@modelcontextprotocol/ext-apps';

type Preview = {job:{id:string;state:string;attempts:number;error:string|null};download_url:string|null};
const bridge = new App({name:'Research Slide Agent',version:'0.1.0'},{});
let receive: (data:Preview)=>void = ()=>{};
let fail: (error:string)=>void = ()=>{};
bridge.ontoolresult = result => {if(result.structuredContent) receive(result.structuredContent as unknown as Preview)};
const connected=bridge.connect().catch(error=>fail(String(error)));

function Viewer(){
  const [data,setData]=useState<Preview|null>(null);
  const [error,setError]=useState('');
  const [busy,setBusy]=useState(false);
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
  return <main style={{fontFamily:'system-ui',color:'var(--color-text-primary,#182537)',padding:16}}>
    <h2>Research Slide Agent</h2>
    {error && <p role="alert">{error}</p>}
    {!data ? <p>スライドの情報を待っています。UIが利用できない場合は get_preview のURLをご利用ください。</p> : <>
      <p role="status">状態: {data.job.state} / 試行: {data.job.attempts}/3{data.job.error && ` / ${data.job.error}`}</p>
      <nav style={{display:'flex',gap:8,flexWrap:'wrap'}} aria-label="操作">
        <button disabled={busy} onClick={()=>void refresh()}>再読み込み</button>
        {data.job.state==='failed' && <button disabled={busy||data.job.attempts>=3} onClick={()=>void retry()}>再実行</button>}
        {data.download_url && <button onClick={()=>void bridge.openLink({url:data.download_url!}).catch(e=>setError(String(e)))}>PPTXをダウンロード</button>}
      </nav>
    </>}
  </main>
}
createRoot(document.getElementById('root')!).render(<Viewer/>);

if(location.protocol==='file:'){location.replace('http://127.0.0.1:4173/');}
const API_BASE=(window.GPX_TERRAIN_CONFIG?.apiBase||'').replace(/\/$/,'');
const apiUrl=path=>API_BASE+path;
const assetUrl=path=>/^https?:\/\//.test(path)?path:API_BASE+path;
const $=id=>document.getElementById(id);
const state={file:null,gpxText:null,pointCount:0,distance:0,route:[],stage:1,jobId:null,finalBundle:null,pollToken:0,autoResumed:false,draftMode:false,submitting:false,serviceOnline:false,creative:null,creativeDirty:null,selectedTitleId:null,selectedLogoId:null};
const ACTIVE_TASK_KEY='gpxTerrainLab.activeTask.v1';
const TASK_LIST_KEY='gpxTerrainLab.taskList.v1';
const CLIENT_ID_KEY='gpxTerrainLab.anonymousClient.v1';
function createAnonymousClientId(){
  if(globalThis.crypto?.randomUUID)return globalThis.crypto.randomUUID();
  const bytes=new Uint8Array(16);
  if(globalThis.crypto?.getRandomValues)globalThis.crypto.getRandomValues(bytes);else for(let i=0;i<bytes.length;i++)bytes[i]=Math.floor(Math.random()*256);
  bytes[6]=(bytes[6]&15)|64;bytes[8]=(bytes[8]&63)|128;
  const hex=[...bytes].map(value=>value.toString(16).padStart(2,'0')).join('');
  return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
}
const CLIENT_ID=localStorage.getItem(CLIENT_ID_KEY)||createAnonymousClientId();localStorage.setItem(CLIENT_ID_KEY,CLIENT_ID);
function clientIdForJob(jobId){
  const saved=taskList().find(item=>item.jobId===jobId)?.clientId;
  if(saved)return saved;
  try{const active=JSON.parse(localStorage.getItem(ACTIVE_TASK_KEY)||'null');if(active?.jobId===jobId&&active.clientId)return active.clientId}catch(_){}
  return CLIENT_ID;
}
function clientIdForAsset(path){const match=String(path||'').match(/\/generated\/(WEB_[^/]+)\//);return match?clientIdForJob(decodeURIComponent(match[1])):CLIENT_ID}
const authorizedAssetUrl=path=>{const url=assetUrl(path);return `${url}${url.includes('?')?'&':'?'}client_id=${encodeURIComponent(clientIdForAsset(path))}`};
const escapeHtml=value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const PREVIEW_SLOTS=[
  {label:'装配透视',purpose:'看沙盘、参考底座、红轨与蓝水的整体关系'},
  {label:'顶视关系',purpose:'看轨迹、水系、边界和文字位置是否冲突'},
  {label:'侧视高度',purpose:'看 Z 轴、地形高度与嵌合关系是否合理'},
  {label:'底部视图',purpose:'用与前三机位一致的 Blender 底视图核对标题、日期、里程与 Logo'}
];
const PREVIEW_REQUIRED_VIEWS=3;
const FINAL_SLOTS=[
  {label:'最终装配',purpose:'看最终底座、文字、Logo 与全部安装件'},
  {label:'最终顶视',purpose:'看最终轮廓、颜色与四件装配关系'},
  {label:'最终侧视',purpose:'看打印姿态、Z 范围和装配高度'}
];
function taskList(){try{return JSON.parse(localStorage.getItem(TASK_LIST_KEY)||'[]')}catch(_){return []}}
function renderTaskList(selected){const items=taskList(),select=$('task-switch'),draft=`<option value="" ${selected?'':'selected'}>＋ 新任务草稿</option>`;select.innerHTML=draft+items.map((item,index)=>`<option value="${item.jobId}" ${item.jobId===selected?'selected':''}>任务 ${items.length-index} · ${item.jobId.slice(4,24)}</option>`).join('');select.hidden=!items.length}
const stateLabel=value=>({QUEUED:'排队中',RUNNING:'生成中',PREVIEW_READY:'仿真完成',FINAL_READY:'可下载',FAILED:'需要处理'})[value]||value||'等待';
function showTaskReceipt(jobId,message){$('task-receipt').hidden=false;$('task-receipt').classList.add('has-tasks');$('task-receipt-title').textContent='✓ 任务已提交';$('task-receipt-id').textContent=`任务号：${jobId}`;$('task-receipt-state').textContent=message||'后台处理中';}
function setServiceHealth(ok,message){state.serviceOnline=ok;const pill=$('service-health');pill.classList.toggle('offline',!ok);pill.querySelector('span').textContent=message||(ok?'制作服务在线':'制作服务离线')}
async function checkServiceHealth(){try{const response=await fetch(apiUrl('/api/health'),{cache:'no-store'}),result=await readJson(response);if(!response.ok||!result.ok)throw new Error(result.error||'健康检查失败');setServiceHealth(true,'制作服务在线');return true}catch(error){setServiceHealth(false,'制作服务离线');return false}}
function updateEmptySlotStatus(galleryId,message){document.querySelectorAll(`#${galleryId} .stage-image-slot>em`).forEach(item=>item.textContent=message)}
function updateQueueReceipt(status){if(!status?.job_id)return;showTaskReceipt(status.job_id,status.message);const q=status.queue||{};$('task-queue-summary').textContent=status.state==='RUNNING'?'正在后台制作，可以安全关闭页面。':status.state==='QUEUED'?`排队第 ${q.position||1} 位，前方 ${q.ahead||0} 个任务；无需重复提交。`:'任务状态已更新。';$('task-steps').innerHTML=(q.steps||[]).map(step=>`<li class="${step.state}">${step.label}</li>`).join('');const stage=status.stage||'',slotStatus={preview:'等待处理',route_profile:'读取路线',trailprint3d:'生成地形',blender_preview:'生成预览',creative:'等待创意确认',production:'制作文件',packaging:'打印检查',complete:'可下载',final:'可下载'}[stage]||'处理中';if(['route_profile','trailprint3d','blender_preview','preview','creative'].includes(stage)){$('preview-stage-note').textContent=status.state==='PREVIEW_READY'?'预览完成':status.message||'正在生成';updateEmptySlotStatus('preview-gallery',slotStatus)}if(['production','packaging','complete','final'].includes(stage)){$('preview-stage-note').textContent='预览完成';$('final-stage-note').textContent=status.state==='FINAL_READY'?'检查完成':status.message||'正在制作';updateEmptySlotStatus('final-gallery',slotStatus)}}
async function refreshTaskCenter(){
  try{
    const response=await fetch(apiUrl(`/api/anonymous-clients/${CLIENT_ID}/jobs`)),data=await readJson(response);if(!response.ok)throw new Error(data.error||'任务中心读取失败');
    const byId=new Map((data.jobs||[]).map(item=>[item.job_id,item]));
    await Promise.all(taskList().slice(0,20).map(async item=>{if(byId.has(item.jobId))return;try{const r=await fetch(apiUrl(`/api/jobs/${encodeURIComponent(item.jobId)}?client_id=${encodeURIComponent(clientIdForJob(item.jobId))}`)),s=await readJson(r);if(r.ok)byId.set(item.jobId,{job_id:item.jobId,title:'历史任务',...s})}catch(_){}}));
    const jobs=[...byId.values()].sort((a,b)=>(b.created_at||'').localeCompare(a.created_at||''));
    if(jobs.length){
      const previous=taskList(),byTask=new Map(previous.map(item=>[item.jobId,item]));
      jobs.forEach(item=>{const old=byTask.get(item.job_id);byTask.set(item.job_id,{jobId:item.job_id,request:item.request||old?.request||'preview',clientId:old?.clientId||CLIENT_ID,updatedAt:Date.parse(item.updated_at||item.created_at||'')||Date.now()})});
      localStorage.setItem(TASK_LIST_KEY,JSON.stringify([...byTask.values()].sort((a,b)=>(b.updatedAt||0)-(a.updatedAt||0)).slice(0,20)));
      $('task-receipt').classList.add('has-tasks');renderTaskList(state.jobId);
    }
    const queue=data.queue||{},total=(queue.running_count||0)+(queue.queued_count||0);
    $('queue-global').textContent=`${queue.worker_capacity||1} 个制作通道 · ${total} 个任务`;
    $('queue-total').textContent=total;$('queue-running').textContent=queue.running_count||0;$('queue-waiting').textContent=queue.queued_count||0;
    const stageLabels={preview:'A·待确认',route_profile:'A·GPX分析',trailprint3d:'A·地形水系',blender_preview:'A·三机位',creative:'A·创意确认',production:'B·生成5+1',packaging:'B·Bambu QA',final:'B·可下载'};
    const stageCounts=queue.stage_counts||{};$('queue-stage-bars').innerHTML=Object.keys(stageLabels).map(key=>`<span class="${stageCounts[key]?'active':''}">${stageLabels[key]} ${stageCounts[key]||0}</span>`).join('');
    $('task-cards').innerHTML=jobs.length?jobs.map(item=>`<article class="task-card ${item.job_id===state.jobId?'active':''}" role="button" tabindex="0" aria-label="查看任务 ${escapeHtml(item.title||'匿名任务')}" data-job-id="${item.job_id}" data-request="${item.request||'preview'}"><header><b>${escapeHtml(item.title||'匿名任务')}</b><em>${stateLabel(item.state)}</em></header><p>${escapeHtml(item.message||'等待状态更新')}</p><progress max="100" value="${item.progress||0}"></progress><footer><span>${item.progress||0}% · 前方 ${item.queue?.ahead||0} 个</span><span>${item.job_id.slice(4,24)}</span></footer></article>`).join(''):'<article class="task-empty"><b>还没有任务</b><span>上传 GPX 后，这里会实时出现任务卡片。</span></article><article class="task-placeholder"><i></i><i></i><i></i></article><article class="task-placeholder"><i></i><i></i><i></i></article>';
    $('task-cards').querySelectorAll('.task-card').forEach(card=>{card.onclick=()=>openTask(card.dataset.jobId,card.dataset.request);card.onkeydown=event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();card.click()}}});
    if(!localStorage.getItem(ACTIVE_TASK_KEY)&&!state.draftMode&&!state.autoResumed){const candidate=jobs.find(item=>item.state==='RUNNING')||jobs.find(item=>item.state==='QUEUED');if(candidate){state.autoResumed=true;const own=taskList().find(item=>item.jobId===candidate.job_id);openTask(candidate.job_id,own?.request||candidate.request||'preview')}}
  }catch(error){$('queue-global').textContent=`任务中心暂时离线 · ${error.message}`}
}
function rememberTask(jobId,request){const old=taskList().find(item=>item.jobId===jobId),active={jobId,request,clientId:old?.clientId||CLIENT_ID,updatedAt:Date.now()},items=taskList().filter(item=>item.jobId!==jobId);items.unshift(active);localStorage.setItem(TASK_LIST_KEY,JSON.stringify(items.slice(0,20)));localStorage.setItem(ACTIVE_TASK_KEY,JSON.stringify(active));renderTaskList(jobId);showTaskReceipt(jobId,request==='final'?'打印文件制作中':'模型预览生成中');$('simulate').disabled=true;$('gpx').disabled=true;}
function releaseTask(preserve=false){if(!preserve)localStorage.removeItem(ACTIVE_TASK_KEY);$('gpx').disabled=false;}
function prepareAnotherTask(){state.pollToken++;state.draftMode=true;releaseTask();setEngineeringLocked(false);renderCreative(null);$('task-receipt-title').textContent='新任务';$('task-receipt-id').textContent='等待上传 GPX';$('task-receipt-state').textContent='已有任务仍在后台继续';$('task-queue-summary').textContent='选择新文件后切换到新任务；旧任务可随时从右侧队列查看。';$('task-steps').innerHTML='<li>读取路线</li><li>生成预览</li><li>确认创意</li><li>制作文件</li><li>检查下载</li>';$('gpx').disabled=false;$('gpx').value='';state.file=null;state.gpxText=null;state.jobId=null;state.finalBundle=null;$('file-name').textContent='上传 GPX';$('file-facts').textContent='已有后台任务不会取消';$('file-action').textContent='选择文件';$('next').disabled=true;$('simulate').disabled=true;$('preview-status').textContent='● 等待上传';$('preview-title').textContent='上传 GPX，开始制作';$('output-live').textContent='等待预览';initPreviewSlots();renderTaskList(null);goStage(1);refreshTaskCenter()}
function openTask(jobId,request){state.pollToken++;state.draftMode=false;const active={jobId,request,clientId:clientIdForJob(jobId),updatedAt:Date.now()};localStorage.setItem(ACTIVE_TASK_KEY,JSON.stringify(active));state.finalBundle=null;renderCreative(null);setEngineeringLocked(true);initPreviewSlots();resumeActiveTask();document.querySelector('.preview-card').scrollIntoView({behavior:'smooth',block:'center'})}
async function readJson(response){const text=await response.text();try{return JSON.parse(text)}catch(_){throw new Error(response.status===404?'后端接口不存在，请确认 4174 服务已启动':'后端返回了非 JSON 内容，请刷新页面或检查 4174 服务')}}

function hav(a,b){const r=6371,d=Math.PI/180,la=(b[1]-a[1])*d,lo=(b[0]-a[0])*d,q=Math.sin(la/2)**2+Math.cos(a[1]*d)*Math.cos(b[1]*d)*Math.sin(lo/2)**2;return 2*r*Math.asin(Math.sqrt(q))}

function normalizedRoute(width,height){
  if(!state.route.length)return [];
  const xs=state.route.map(p=>p[0]),ys=state.route.map(p=>p[1]),minX=Math.min(...xs),maxX=Math.max(...xs),minY=Math.min(...ys),maxY=Math.max(...ys),spanX=Math.max(maxX-minX,1e-9),spanY=Math.max(maxY-minY,1e-9),scale=Math.min(width*.62/spanX,height*.55/spanY),step=Math.max(1,Math.floor(state.route.length/500));
  return state.route.filter((_,i)=>i%step===0||i===state.route.length-1).map(([lon,lat])=>[(lon-(minX+maxX)/2)*scale,-(lat-(minY+maxY)/2)*scale]);
}

function draw(){
  const c=$("terrain"),dpr=devicePixelRatio||1,b=c.getBoundingClientRect();c.width=b.width*dpr;c.height=b.height*dpr;const x=c.getContext("2d");x.scale(dpr,dpr);const w=b.width,h=b.height;x.translate(w/2,h/2);const radius=Math.min(w*.46,h*.46/Math.sin(Math.PI/3));x.beginPath();for(let i=0;i<6;i++){const a=Math.PI/3*i,X=Math.cos(a)*radius,Y=Math.sin(a)*radius;i?x.lineTo(X,Y):x.moveTo(X,Y)}x.closePath();x.clip();const g=x.createLinearGradient(0,-h/2,0,h/2);g.addColorStop(0,"#90979b");g.addColorStop(.26,"#765438");g.addColorStop(.49,"#506f3e");g.addColorStop(1,"#284c35");x.fillStyle=g;x.fillRect(-w/2,-h/2,w,h);
  for(let y=-170;y<180;y+=9){x.beginPath();for(let X=-250;X<=250;X+=5){const Y=y+Math.sin(X*.065+y*.025)*8+Math.cos(X*.018-y*.05)*5;X===-250?x.moveTo(X,Y):x.lineTo(X,Y)}x.strokeStyle="rgba(237,245,223,.16)";x.stroke()}
  const river=[[-.40,.25],[-.29,.11],[-.17,.19],[-.04,.04],[.09,.15],[.20,-.02],[.31,-.13],[.40,-.31]].map(([px,py])=>[px*w,py*h]);x.beginPath();river.forEach((p,i)=>i?x.lineTo(...p):x.moveTo(...p));x.strokeStyle="#2f74c8";x.lineWidth=4;x.lineCap="round";x.lineJoin="round";x.stroke();
  const trail=normalizedRoute(w,h);if(trail.length){x.beginPath();trail.forEach((p,i)=>i?x.lineTo(...p):x.moveTo(...p));x.strokeStyle="#db3f31";x.lineWidth=7;x.lineCap="round";x.lineJoin="round";x.stroke();const start=trail[0],end=trail[trail.length-1];x.fillStyle="#db3f31";x.beginPath();x.arc(start[0],start[1],7,0,Math.PI*2);x.fill();x.lineWidth=4;x.beginPath();x.arc(end[0],end[1],10,0,Math.PI*2);x.stroke();x.beginPath();x.arc(end[0],end[1],3,0,Math.PI*2);x.fill()}
}

function sync(){const s=+$('size').value,r=+$('resolution').value,e=+$('elevation').value,p=+$('path').value;$('size-v').textContent=s+' mm';$('resolution-v').textContent=r;$('elevation-v').textContent=e.toFixed(2);$('path-v').textContent=p.toFixed(2)+' mm';$('meta-size').textContent=s+' mm';$('meta-r').textContent='R'+r;$('preview-title').textContent=$('title').value||'上传 GPX，开始制作';const n=[s!==100,r!==8,e!==1.8,p!==1.6].filter(Boolean).length;$('baseline').className=n?'warn':'pass';$('baseline').textContent=n?'! '+n+' 项参数已调整':'✓ 已采用推荐参数'}
function syncLive(){const heightLimit=(+$('size').value*.15).toFixed(1),city=$('city').checked;$('engineering-live').textContent=state.file?`${state.distance.toFixed(2)} km · ${state.pointCount} 点 · ${$('size').value} mm / R${$('resolution').value} · 限高 ${heightLimit} mm`:'上传后自动计算';$('creative-live').textContent=$('title').value||'上传后采用文件名';$('elements-live').textContent=`水系${$('water').checked?'开启':'关闭'} · 森林${$('forest').checked?'开启':'关闭'} · 城市${city?'开启（陶土橙）':'关闭'}`;$('terrain-color-title').textContent=city?'四色沙盘':'三色沙盘';$('terrain-color-list').textContent=city?'绿·棕·灰·陶土橙':'绿·棕·灰'}
function setEngineeringLocked(locked){
  ['size','resolution','elevation','path','water','forest','city','reset'].forEach(id=>$(id).disabled=locked);
  $('stage-2')?.classList.toggle('locked',locked);
  $('stage-3')?.classList.toggle('engineering-locked',locked);
}

function creativeAction(){
  if(state.finalBundle)return'download';
  if(state.creativeDirty)return state.creativeDirty;
  return {TITLE_SELECTION:'title',LOGO_SELECTION:'logo',CONFIRMATION:'confirm',CONFIRMED:'final'}[state.creative?.stage]||null;
}
function updateCreativeAction(){
  const button=$('download'),action=creativeAction();
  if(!state.jobId||!action){button.hidden=true;button.disabled=true;return}
  const labels={download:'下载完整套装 <span>↓</span>',title:'确认标题，生成 Logo <span>→</span>',logo:'确认 Logo，生成底面校样 <span>→</span>',confirm:'确认底面校样 <span>→</span>',final:'异步生成最终 5+1 <span>→</span>'};
  button.hidden=false;button.disabled=false;button.innerHTML=labels[action];
}
function syncCreativeProofPreview(creative){
  const gallery=$('preview-gallery');
  if(!gallery)return;
  const slot=PREVIEW_SLOTS[3],existing=gallery.children[3],engineeringViews=[...gallery.querySelectorAll('button:not([data-creative-proof])')].length;
  if(!creative?.proof){
    if(!existing||existing.dataset.creativeProof){
      const empty=document.createElement('div');empty.className='stage-image-slot';empty.innerHTML=`<i class="slot-hex"><span></span></i><strong>A4 · ${slot.label}</strong><small>${slot.purpose}</small><em>等待创意确认</em>`;
      if(existing)existing.replaceWith(empty);else gallery.appendChild(empty);
    }
    $('preview-count').textContent=`${engineeringViews} / ${PREVIEW_SLOTS.length}`;
    return;
  }
  const imageUrl=authorizedAssetUrl(creative.proof.render_url||creative.proof.url)+'&t='+Date.now(),button=document.createElement('button');
  button.dataset.creativeProof='true';
  button.innerHTML=`<img src="${imageUrl}" alt="Blender 底部视图"><span><b>${slot.label}</b><small>${slot.purpose}</small></span><em>点击放大</em>`;
  button.onclick=()=>openLightbox(imageUrl,slot.label,slot.purpose);
  if(existing)existing.replaceWith(button);else gallery.appendChild(button);
  $('preview-count').textContent=`${engineeringViews+1} / ${PREVIEW_SLOTS.length}`;
}
function renderCreative(creative,preserveDirty=false){
  const root=$('creative-workflow'),titles=$('title-options'),logos=$('logo-options'),proof=$('creative-proof');
  state.creative=creative||null;
  if(!creative){state.creativeDirty=null;state.selectedTitleId=null;state.selectedLogoId=null;root.hidden=true;titles.innerHTML='';logos.innerHTML='';proof.hidden=true;syncCreativeProofPreview(null);updateCreativeAction();return}
  root.hidden=false;
  if(!preserveDirty){state.creativeDirty=null;state.selectedTitleId=creative.selected_title_id||creative.title_candidates?.[0]?.id||null;state.selectedLogoId=creative.selected_logo_id||creative.logo_candidates?.[0]?.id||null}
  titles.innerHTML='';
  (creative.title_candidates||[]).forEach(item=>{const button=document.createElement('button');button.type='button';button.className=`choice-card ${state.selectedTitleId===item.id?'selected':''}`;button.innerHTML=`<b>${escapeHtml(item.title)}</b><small>${escapeHtml(item.label)} · ${escapeHtml(item.reason)}</small><em>${item.fit==='PASS'?'适合打印':'需缩短'}</em>`;button.onclick=()=>{state.selectedTitleId=item.id;state.creativeDirty='title';$('title').value=item.title;sync();syncLive();renderCreative(state.creative,true)};titles.appendChild(button)});
  const logoItems=creative.logo_candidates||[];logos.hidden=!logoItems.length;logos.innerHTML='';
  logoItems.forEach(item=>{const button=document.createElement('button'),url=authorizedAssetUrl(item.url);button.type='button';button.className=`choice-card ${state.selectedLogoId===item.id?'selected':''}`;button.innerHTML=`<img src="${url}" alt="${escapeHtml(item.label)}"><span><b>${escapeHtml(item.label)}</b><small>${escapeHtml(item.description)}</small><em>${item.qa==='PASS'?'可打印':'需复核'}</em></span>`;button.onclick=()=>{state.selectedLogoId=item.id;state.creativeDirty='logo';renderCreative(state.creative,true)};logos.appendChild(button)});
  proof.hidden=!creative.proof;
  if(creative.proof){const proofUrl=authorizedAssetUrl(creative.proof.render_url||creative.proof.url)+'&t='+Date.now();$('creative-proof-image').src=proofUrl;proof.onclick=()=>openLightbox(proofUrl,'Blender 底部视图',`与前三机位统一渲染；制造仍以同源 SVG 与固定奖牌框 ${creative.proof.dimensions?.frame_spec||''} 为准。`)}
  const action=creativeAction(),copy={title:['先选标题','标题确认后才生成相关 Logo'],logo:['再选 Logo','Logo 与标题使用同一主题'],confirm:['核对底面校样','确认标题、日期、里程、Logo 与固定尺寸'],final:['创意已确认','工程不重算，可以生成最终 5+1']}[action]||['创意已确认','选择已保存'];
  $('creative-step-label').textContent=copy[0];$('creative-help').textContent=copy[1];
  if(creative.selected_title&&!state.creativeDirty)$('title').value=creative.selected_title;
  syncCreativeProofPreview(creative);sync();syncLive();updateCreativeAction();
}
async function postCreative(action,payload){
  if(!state.jobId)throw new Error('当前没有可确认的任务');
  const response=await fetch(apiUrl(`/api/jobs/${encodeURIComponent(state.jobId)}/creative/${action}`),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({client_id:clientIdForJob(state.jobId),...payload})}),accepted=await readJson(response);
  if(!response.ok)throw new Error(accepted.error||'创意选择保存失败');
  renderCreative(accepted.creative);showTaskReceipt(state.jobId,action==='confirm'?'创意已确认，可以制作打印文件':'创意选择已保存');refreshTaskCenter();return accepted;
}

function goStage(stage){
  state.stage=Math.max(1,Math.min(4,stage));document.body.dataset.stage=state.stage;document.querySelectorAll('.stage-tab').forEach(b=>b.classList.toggle('active',+b.dataset.stage===state.stage));
  $('previous').hidden=true;$('next').hidden=true;$('simulate').hidden=false;$('next').disabled=!state.file;updateCreativeAction();
}

['size','resolution','elevation','path'].forEach(id=>$(id).addEventListener('input',()=>{sync();syncLive()}));
$('title').addEventListener('input',()=>{sync();syncLive();if(state.creative){state.selectedTitleId='CUSTOM';state.creativeDirty='title';renderCreative(state.creative,true)}});
$('date').addEventListener('change',()=>{if(state.creative?.selected_logo_id){state.selectedLogoId=state.creative.selected_logo_id;state.creativeDirty='logo';renderCreative(state.creative,true)}});
$('water').addEventListener('change',syncLive);$('forest').addEventListener('change',syncLive);$('city').addEventListener('change',syncLive);
$('reset').onclick=()=>{$('size').value=100;$('resolution').value=8;$('elevation').value=1.8;$('path').value=1.6;sync()};
document.querySelectorAll('.stage-tab').forEach(b=>b.onclick=()=>goStage(+b.dataset.stage));
$('previous').onclick=()=>goStage(state.stage-1);$('next').onclick=()=>goStage(state.stage+1);
$('new-task').onclick=prepareAnotherTask;
$('task-switch').onchange=()=>{const value=$('task-switch').value;if(!value){prepareAnotherTask();return}const item=taskList().find(task=>task.jobId===value);if(item)openTask(item.jobId,item.request)};

$('gpx').onchange=async e=>{const f=e.target.files[0];if(!f)return;const source=await f.text(),xml=new DOMParser().parseFromString(source,'application/xml'),nodes=[...xml.getElementsByTagNameNS('*','trkpt')],pts=nodes.map(n=>[+n.getAttribute('lon'),+n.getAttribute('lat')]).filter(p=>Number.isFinite(p[0])&&Number.isFinite(p[1]));if(!pts.length){$('file-facts').textContent='没有找到有效轨迹点；请使用两步路导出的 GPX';return}state.file=f.name;state.gpxText=source;state.pointCount=pts.length;state.route=pts;state.distance=pts.slice(1).reduce((s,p,i)=>s+hav(pts[i],p),0);state.jobId=null;state.finalBundle=null;setEngineeringLocked(false);renderCreative(null);const inferredTitle=f.name.replace(/\.gpx$/i,'').trim();$('title').value=inferredTitle;sync();$('file-name').textContent=f.name;$('file-facts').textContent=`${pts.length} 个轨迹点 · ${state.distance.toFixed(2)} km`;$('file-action').textContent='已读取';$('next').disabled=false;$('download').hidden=true;$('simulate').disabled=false;$('preview-status').textContent='● 路线已读取';initPreviewSlots();document.querySelector('.route-strip').classList.remove('show-render');draw();syncLive()};

function buildJob(){const name=$('title').value||state.file.replace(/\.gpx$/i,''),water=$('water').checked,size=+$('size').value;return {schema_version:'1.2-web',preview:{quick_preview:'gpx_shape_only',final_preview:'pending_blender_render'},route:{name,gpx:state.file,facts:{points:state.pointCount,distance_km:+state.distance.toFixed(3)}},customer_input:{display_date:$('date').value,title:name},engineering:{source:'TrailPrint3D',shape:'HEXAGON',object_size_mm:size,terrain_resolution:+$('resolution').value,elevation_scale:+$('elevation').value,fixed_elevation_scale_10mm:true,min_terrain_thickness_mm:2,max_terrain_height_mm:+(size*.15).toFixed(1),path_thickness_mm:+$('path').value,path_scale:.8,single_color_trail:true,element_mode:'SINGLECOLORMODE_REMESH',trailprint_water:{water,big_rivers:water,small_rivers:water,include_ocean:water,river_width:1,water_threshold:1,min_island_area:2,coastline_simplify:.1,merge_into_trailprint_terrain:true},trailprint_elements:{forests:$('forest').checked,forest_threshold:10,city_boundaries:$('city').checked,city_threshold:1},bambu:{outputs_3mf:5,outputs_blend:1,colors:['#3F8E43','#6F5034','#858C91','#7A4A20','#D93025','#2563B8']}},deliverables:{three_mf_count:5,blend_count:1,final_dir:'final'}}}

function placeholderSlots(target,slots,message,phase){target.className='stage-image-grid placeholders';target.innerHTML=slots.map((slot,index)=>`<div class="stage-image-slot"><i class="slot-hex"><span></span></i><strong>${phase}${index+1} · ${slot.label}</strong><small>${slot.purpose}</small><em>${message}</em></div>`).join('')}
function initPreviewSlots(){placeholderSlots($('preview-gallery'),PREVIEW_SLOTS,'等待任务','A');placeholderSlots($('final-gallery'),FINAL_SLOTS,'等待 A 通过','B');$('preview-count').textContent=`0 / ${PREVIEW_SLOTS.length}`;$('final-count').textContent=`0 / ${FINAL_SLOTS.length}`;$('preview-stage-note').textContent='等待提交';$('final-stage-note').textContent='等待 A 通过';document.querySelectorAll('.image-stage').forEach(stage=>stage.classList.remove('complete'));document.querySelector('.route-strip').classList.remove('show-render');$('coverage').className='coverage';$('coverage').innerHTML='<b>预计交付</b><span>01 等待</span><span>02 等待</span><span>03 等待</span><span>04 等待</span><span>05 等待</span><span>06 等待</span>'}

function openLightbox(url,label,purpose){$('lightbox-image').src=url;$('lightbox-title').textContent=label;$('lightbox-purpose').textContent=purpose||'';const modal=$('image-lightbox');if(!modal.open)modal.showModal()}
$('lightbox-close').onclick=()=>$('image-lightbox').close();$('image-lightbox').onclick=event=>{if(event.target===$('image-lightbox'))$('image-lightbox').close()};

function showPreviewSet(result,phase='preview'){
  const isFinal=phase==='final',gallery=$(isFinal?'final-gallery':'preview-gallery'),count=$(isFinal?'final-count':'preview-count'),expected=isFinal?FINAL_SLOTS:PREVIEW_SLOTS,views=result.previews||[],stamp='&t='+Date.now();gallery.className='stage-image-grid';gallery.innerHTML='';
  const total=Math.max(expected.length,views.length);for(let index=0;index<total;index++){const view=views[index],slot=expected[index]||{label:`图 ${index+1}`,purpose:'补充核验机位'};if(!view){const empty=document.createElement('div');empty.className='stage-image-slot';empty.innerHTML=`<i class="slot-hex"><span></span></i><strong>${isFinal?'B':'A'}${index+1} · ${slot.label}</strong><small>${slot.purpose}</small><em>${!isFinal&&index===3?'等待创意确认':'等待'}</em>`;gallery.appendChild(empty);continue}const imageUrl=authorizedAssetUrl(view.url)+stamp,button=document.createElement('button');button.innerHTML=`<img src="${imageUrl}" alt="${escapeHtml(view.label)}"><span><b>${escapeHtml(view.label)}</b><small>${escapeHtml(slot.purpose)}</small></span><em>点击放大</em>`;button.onclick=()=>openLightbox(imageUrl,view.label,slot.purpose);gallery.appendChild(button)}count.textContent=`${views.length} / ${total}`;const stage=gallery.closest('.image-stage'),complete=views.length>=(isFinal?expected.length:PREVIEW_REQUIRED_VIEWS);stage.classList.toggle('complete',complete);$(isFinal?'final-stage-note':'preview-stage-note').textContent=complete?(isFinal?'B 已完成 · 可下载':'A 已完成 · 可进入 B'):(isFinal?'B 生成中':'A 仿真中');
  if(!isFinal){const profile=result.route_profile,mode=profile?.mode||'LOCAL_HIKE',modeLabel={LOCAL_HIKE:'局部徒步',LONG_HIKE:'长线徒步',REGIONAL_OVERVIEW:'区域概览',MULTI_TILE_REQUIRED:'超长路线候选'}[mode]||mode,water=mode==='REGIONAL_OVERVIEW'?'主要水系可选':'水系 ✓',heightPolicy=result.terrain_height_policy;$('coverage').innerHTML=`<b>工程仿真 · ${modeLabel}</b><span class="ready">地形 ✓</span><span class="ready">轨迹 ✓</span><span class="${mode==='REGIONAL_OVERVIEW'?'reference':'ready'}">${water}</span><span class="pending">最终 5+1 待生成</span>`;if(heightPolicy){const actual=Number(heightPolicy.actual_terrain_height_mm||0).toFixed(1),limit=Number(heightPolicy.max_terrain_height_mm||0).toFixed(1),scale=Number(heightPolicy.effective_elevation_scale||0).toFixed(2);$('engineering-live').textContent=`实际厚度 ${actual} mm / 上限 ${limit} mm · 有效高程 ${scale}`}$('step-hint').textContent=heightPolicy?.height_limited?`地形已自动限高：请求 ${heightPolicy.requested_elevation_scale}，有效 ${Number(heightPolicy.effective_elevation_scale).toFixed(2)}。`:profile&&mode!=='LOCAL_HIKE'?`${modeLabel}：${profile.facts.distance_km} km，控制点 ${profile.facts.points} → ${profile.model_points}。`:$('step-hint').textContent;setEngineeringLocked(true);if(Object.prototype.hasOwnProperty.call(result,'creative'))renderCreative(result.creative)}
}

function humanSize(bytes){return bytes>1024*1024?(bytes/1024/1024).toFixed(1)+' MB':Math.ceil(bytes/1024)+' KB'}
const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function fetchJobStatus(jobId,maxNotFoundRetries=6){
  for(let attempt=0;;attempt++){
    const response=await fetch(apiUrl(`/api/jobs/${encodeURIComponent(jobId)}?client_id=${encodeURIComponent(clientIdForJob(jobId))}`)),status=await readJson(response);
    if(response.ok)return status;
    if(response.status===404&&attempt<maxNotFoundRetries){await wait(Math.min(1500,300*(attempt+1)));continue}
    throw new Error(status.error||'读取任务状态失败');
  }
}
async function pollJob(jobId,readyStates,onProgress){
  const token=++state.pollToken;
  for(;;){
    if(token!==state.pollToken){const error=new Error('任务视图已切换');error.code='POLL_CANCELLED';throw error}
    const status=await fetchJobStatus(jobId);
    onProgress?.(status);
    updateQueueReceipt(status);
    if(status.state==='FAILED')throw new Error(status.error||status.message||'后台任务失败');
    if(readyStates.includes(status.state))return status.result||status;
    await wait(2000);
  }
}
function showFinalFiles(result,recovered=false){
  if(result.job_id){const base=`/generated/${result.job_id}/review/`;showPreviewSet({previews:[{label:'装配透视',url:base+'blender_preview.png'},{label:'顶视关系',url:base+'blender_preview_top.png'},{label:'侧视高度',url:base+'blender_preview_side.png'}]},'preview')}
  if(result.previews)showPreviewSet(result,'final');
  $("output-live").textContent="5 + 1 已完成 · QA PASS";const coverage=$('coverage');coverage.className='coverage downloads';coverage.innerHTML=`<b>${recovered?'上一次已完成任务 · 可直接下载':'本次上传 GPX 实时生成 · QA 全部通过'}</b>`;result.files.forEach(item=>{const link=document.createElement('a');link.href=authorizedAssetUrl(item.url);link.download='';link.innerHTML=`<strong>${item.key} ${item.label}</strong><small>${humanSize(item.bytes)} · SHA ${item.sha256.slice(0,8)}…</small><em>PASS · 下载</em>`;coverage.appendChild(link)});const all=document.createElement('a');all.className='bundle';all.href=authorizedAssetUrl(result.bundle.url);all.download='';all.innerHTML=`<strong>↓ 下载完整 5+1 套装</strong><small>${humanSize(result.bundle.bytes)} · 含 SHA-256 清单</small>`;coverage.appendChild(all);if(result.preview_url){$('preview-kind').textContent='最终工程三机位预览 · 与交付 Blender 同源';document.querySelector('.preview-truth').textContent='阶段 A 保留 Blender 工程仿真；阶段 B 展示最终交付几何。底座、三色沙盘、红色轨迹和蓝色水系均来自本次任务，3MF 另经 Bambu 容器与颜色映射 QA。'}}

function showEngineeringPreviews(jobId){const base=`/generated/${jobId}/review/`;showPreviewSet({previews:[{label:'装配透视',url:base+'blender_preview.png'},{label:'顶视关系',url:base+'blender_preview_top.png'},{label:'侧视高度',url:base+'blender_preview_side.png'}]},'preview');$('preview-kind').textContent='已完成工程仿真 · 最终 5+1 后台生成中'}

async function resumeActiveTask(){
  let active;try{active=JSON.parse(localStorage.getItem(ACTIVE_TASK_KEY)||'null')}catch(_){releaseTask();return false}
  if(!active?.jobId)return false;
  state.pollToken++;state.jobId=active.jobId;state.finalBundle=null;renderCreative(null);setEngineeringLocked(true);renderTaskList(active.jobId);state.file='恢复中的任务';showTaskReceipt(active.jobId,'正在恢复任务状态');goStage(4);$('simulate').hidden=false;$('simulate').disabled=true;$('gpx').disabled=true;
  try{
    const first=await fetchJobStatus(active.jobId);updateQueueReceipt(first);
    if(first.state==='FAILED')throw new Error(first.error||first.message||'后台任务失败');
    const target=active.request==='final'?'FINAL_READY':'PREVIEW_READY';
    if(target==='FINAL_READY'&&first.state!=='QUEUED')showEngineeringPreviews(active.jobId);
    const result=[target,'FINAL_READY'].includes(first.state)?first.result:await pollJob(active.jobId,[target],status=>showTaskReceipt(active.jobId,`${status.message}（${status.progress||0}%）`));
    if(target==='FINAL_READY'){
      state.finalBundle=authorizedAssetUrl(result.bundle.url);showFinalFiles(result);$("output-live").textContent="5 + 1 已完成 · QA PASS";showTaskReceipt(active.jobId,'任务完成，可以下载');releaseTask(true);updateCreativeAction();
    }else{
      showPreviewSet(result);$("output-live").textContent="工程仿真已完成";showTaskReceipt(active.jobId,'工程仿真完成，请继续创意确认');$('preview-status').textContent='● 工程仿真完成 · 等待创意确认';$('step-hint').textContent='工程参数已冻结；按标题、Logo、底面校样的顺序确认后，才会生成最终 5+1。';updateCreativeAction();
    }
  }catch(error){if(error.code==='POLL_CANCELLED')return false;releaseTask();showTaskReceipt(active.jobId,`任务未完成：${error.message}`);$('simulate').disabled=false;$('simulate').textContent='重新生成预览'}
  return true;
}

$('simulate').onclick=async()=>{
  const button=$('simulate');button.disabled=true;button.textContent='正在连接制作服务…';state.jobId=null;state.finalBundle=null;state.submitting=true;renderCreative(null);setEngineeringLocked(false);$('download').hidden=true;$('preview-status').textContent='● 正在连接制作服务';$('step-hint').textContent='尚未取得任务号，请暂勿刷新或关闭页面。';
  try{
    if(!await checkServiceHealth())throw new Error('制作服务当前离线，请稍后重试');
    button.textContent='正在提交任务…';$('preview-status').textContent='● 正在提交任务';
    const response=await fetch(apiUrl('/api/generate-preview'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({client_id:CLIENT_ID,gpx_text:state.gpxText,job:buildJob()})}),accepted=await readJson(response);
    if(!response.ok)throw new Error(accepted.error||'任务提交失败');if(!accepted.job_id)throw new Error('后端未返回任务号');
    state.jobId=accepted.job_id;rememberTask(state.jobId,'preview');$('preview-status').textContent='● 任务已进入制作队列';$('step-hint').textContent=`任务 ${state.jobId} 已接收；现在可以安全刷新或关闭页面。`;refreshTaskCenter();
    const result=await pollJob(state.jobId,['PREVIEW_READY'],status=>{button.textContent=`后台处理中 ${status.progress||0}%`;$('preview-status').textContent=`● ${status.message}`;$('step-hint').textContent=`任务 ${state.jobId} · 阶段 ${status.stage}`});
    showPreviewSet(result);$("output-live").textContent='Blender 三机位已完成';$('preview-kind').textContent='本次上传 GPX · Blender 三机位实时仿真';$('preview-status').textContent='● 工程仿真完成 · 等待创意确认';$('preview-status').classList.remove('error');$('step-hint').textContent='工程参数已冻结；现在先确认标题，再选择相关 Logo。';button.textContent='仿真已完成（无需重复提交）';updateCreativeAction();
  }catch(error){
    releaseTask();const offline=!state.serviceOnline||error instanceof TypeError||/fetch|离线/i.test(error.message);$('preview-status').textContent=offline?'● 制作服务离线':'● 任务提交失败';$('preview-status').classList.add('error');$('step-hint').textContent=state.jobId?`任务 ${state.jobId} 已保存，可刷新后恢复。`:`任务尚未创建：${error.message}`;button.textContent=offline?'服务恢复后重试':'重新提交任务';
  }finally{state.submitting=false;button.disabled=!!localStorage.getItem(ACTIVE_TASK_KEY)}
};

async function startFinalProduction(){
  const button=$('download');button.disabled=true;button.textContent='正在提交最终任务…';$('preview-status').textContent='● 最终 5+1 准备排队';
  try{
    const response=await fetch(apiUrl('/api/finalize-job'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({job_id:state.jobId,client_id:clientIdForJob(state.jobId)})}),accepted=await readJson(response);if(!response.ok)throw new Error(accepted.error||'最终任务提交失败');
    rememberTask(state.jobId,'final');const result=await pollJob(state.jobId,['FINAL_READY'],status=>{button.textContent=`后台生成 ${status.progress||0}%`;$('preview-status').textContent=`● ${status.message}`;$('step-hint').textContent=`任务 ${state.jobId} · 阶段 ${status.stage}`});
    state.finalBundle=authorizedAssetUrl(result.bundle.url);showTaskReceipt(state.jobId,'任务完成，可以下载');releaseTask(true);showFinalFiles(result);$("output-live").textContent='5 + 1 已完成 · QA PASS';$('preview-kind').textContent='Blender 仿真 + 真机验证交付';$('preview-status').textContent='● 5+1 已生成 · QA PASS';$('preview-status').classList.remove('error');$('step-hint').textContent='最终文件已就绪：可逐件下载，也可下载完整 ZIP。';updateCreativeAction();
  }catch(error){
    releaseTask(true);$('preview-status').textContent='● 最终生成被阻止';$('preview-status').classList.add('error');$('step-hint').textContent=error.message;updateCreativeAction();
  }
}

$('download').onclick=async()=>{
  const action=creativeAction(),button=$('download');
  if(action==='download'){location.href=state.finalBundle;return}
  button.disabled=true;
  try{
    if(action==='title'){
      const custom=state.selectedTitleId==='CUSTOM';
      await postCreative('title',{candidate_id:custom?null:state.selectedTitleId,custom_title:custom?$('title').value:null,display_date:$('date').value});
    }else if(action==='logo'){
      await postCreative('logo',{candidate_id:state.selectedLogoId,display_date:$('date').value});
    }else if(action==='confirm'){
      await postCreative('confirm',{});$('preview-status').textContent='● 创意方案已确认';$('step-hint').textContent='底面校样已锁定；下一步只生成最终文件，不重复计算工程预览。';
    }else if(action==='final'){
      await startFinalProduction();return;
    }
  }catch(error){
    $('preview-status').textContent='● 创意确认未保存';$('preview-status').classList.add('error');$('step-hint').textContent=error.message;
  }finally{if(action!=='final'){button.disabled=false;updateCreativeAction()}}
};

addEventListener('beforeunload',event=>{if(state.submitting&&!state.jobId){event.preventDefault();event.returnValue='任务仍在提交，尚未取得任务号。'}});
addEventListener('resize',draw);sync();draw();initPreviewSlots();goStage(1);checkServiceHealth();refreshTaskCenter();setInterval(()=>{checkServiceHealth();refreshTaskCenter()},5000);resumeActiveTask();

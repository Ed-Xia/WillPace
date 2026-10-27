'use strict';
const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const metrics = {
  leanAngle: ['躯干前倾', '°'], verticalOscillation: ['髋部垂直振幅', 'cm'],
  cadence: ['估计步频', '步/分钟'], leftStrideDistance: ['左脚相对髋部距离', 'cm'],
  rightStrideDistance: ['右脚相对髋部距离', 'cm'], leftKnee: ['左膝角度', '°'],
  rightKnee: ['右膝角度', '°'], leftHip: ['左髋角度', '°'], rightHip: ['右髋角度', '°'],
  leftAnkle: ['左踝角度', '°'], rightAnkle: ['右踝角度', '°'], leftElbow: ['左肘角度', '°'], rightElbow: ['右肘角度', '°']
};
const state = {user:null, reports:[], jobs:[], report:null, pair:null, file:null, fileURL:null,
  stream:null, recorder:null, live:false, recording:false, discardRecording:false, registering:false,
  busy:false, page:'analyze', refreshBusy:false, authEpoch:0, calibration:[], polling:null};
const finite = value => typeof value === 'number' && Number.isFinite(value);
const valueText = (value, digits=1) => finite(value) ? value.toFixed(digits) : '无法评估';
const dateText = value => new Date(value).toLocaleString('zh-CN', {hour12:false});
const baseURL = () => new URL(API_CONFIG.BASE_URL.replace(/\/$/, '') + '/', location.href);
const apiURL = path => new URL(path.replace(/^\//, ''), baseURL()).href;
const mediaURL = path => new URL(path, baseURL()).href;
let toastTimer;
function toast(message) { $('toast').textContent=message; $('toast').hidden=false; clearTimeout(toastTimer); toastTimer=setTimeout(()=>$('toast').hidden=true, 5500); }
async function api(path, {method='GET', body, signal}={}) {
  const headers={};
  if (body && !(body instanceof FormData) && !(body instanceof Blob)) { headers['Content-Type']='application/json'; body=JSON.stringify(body); }
  const response=await fetch(apiURL(path), {method,body,headers,credentials:'include',signal});
  const payload=await response.json();
  if (!response.ok) {
    if (response.status===401 && state.user) { resetAccount(); showAuth(); }
    throw new Error(payload.message || '请求失败');
  }
  return payload.data;
}
function on(id,event,fn) { $(id).addEventListener(event, e=>{if(event==='submit')e.preventDefault();Promise.resolve().then(()=>fn(e)).catch(error=>toast(error.message));}); }
function needUser() { if(state.user) return true; showAuth(); return false; }
function showAuth() { if(!$('auth-dialog').open) $('auth-dialog').showModal(); }
function page(name) {
  if(name!=='analyze' && state.stream) closeCamera();
  if(name!=='detail') $('report-video').pause();
  if(name!=='compare') { $('compare-video-a').pause(); $('compare-video-b').pause(); }
  document.querySelectorAll('.page').forEach(el=>el.hidden=el.id!==`page-${name}`);
  document.querySelectorAll('nav button').forEach(el=>el.classList.toggle('active',el.dataset.page===name));
  state.page=name;
  if(name==='reports') renderReports();
  if(name==='growth') renderGrowth();
}
function profileToForms() {
  const p=state.user.profile;
  for(const prefix of ['capture','profile']) {
    $(`${prefix}-height`).value=p.heightCm || 170;
    $(`${prefix}-view`).value=p.view || 'side';
    $(`${prefix}-direction`).value=p.direction || 'right';
  }
  $('capture-pixels').value='';
  $('profile-nickname').value=p.nickname || state.user.username;
  $('profile-age').value=p.age || '';
  $('profile-gender').value=p.gender || '';
  $('account-label').textContent=p.nickname || state.user.username;
  $('account-btn').textContent='退出登录';
}
function resetAccount() {
  state.authEpoch++; state.user=null; state.jobs=[]; state.reports=[]; state.report=null; state.pair=null;
  closeCamera(); state.file=null;
  if(state.fileURL) URL.revokeObjectURL(state.fileURL);
  state.fileURL=null; $('preview').removeAttribute('src'); $('preview').load(); $('preview').hidden=true;
  for(const id of ['report-video','compare-video-a','compare-video-b']) { $(id).pause(); $(id).removeAttribute('src'); $(id).load(); }
  $('account-label').textContent='尚未登录'; $('account-btn').textContent='登录 / 注册';
  $('file-label').textContent='尚未选择视频'; $('video-file').value='';
  $('live-feedback').hidden=true; $('comparison').hidden=true;
  $('quality-result').textContent='登录后可检查画面质量。'; $('capture-pixels').value='';
  $('calibration-panel').hidden=true; renderJobs(); renderReports(); populateCompare(); page('analyze');
}
async function refresh() {
  if(!state.user || state.refreshBusy) return;
  state.refreshBusy=true; const epoch=state.authEpoch;
  try {
    const [jobs,reports]=await Promise.all([api('analyses'),api('reports')]);
    if(epoch!==state.authEpoch) return;
    state.jobs=jobs; state.reports=reports.list;
    renderJobs(); renderReports(); populateCompare(); if(state.page==='growth') renderGrowth();
  } finally { state.refreshBusy=false; }
}
function renderJobs() {
  $('jobs').classList.toggle('empty',!state.jobs.length);
  $('jobs').innerHTML=state.jobs.length ? state.jobs.slice(0,12).map(job=>`<div class="job"><div><strong>${esc(job.name)}</strong><p>${esc(job.stage)} · ${Number(job.progress)}% ${job.totalFrames ? `· ${job.processedFrames}/${job.totalFrames} 帧`:''}</p><progress max="100" value="${Number(job.progress)}" aria-label="分析进度"></progress>${job.error ? `<p class="error">${esc(job.error)}</p>`:''}</div><div>${job.status==='failed' ? `<button class="secondary" data-retry="${job.analysisId}">重试</button>`:job.status==='completed' ? `<button class="quiet" data-report="${job.reportId}">查看报告 →</button>`:''}</div></div>`).join('') : '暂无任务。选择视频或打开摄像头，开始一次分析。';
}
function renderReports() {
  const query=$('report-search').value.toLowerCase();
  const reports=state.reports.filter(r=>r.reportName.toLowerCase().includes(query));
  $('reports').innerHTML=reports.length ? reports.map(r=>`<button class="report-card" data-report="${r.reportId}"><p class="eyebrow">${r.reportType==='realtime'?'CAMERA SESSION':'VIDEO ANALYSIS'} ${$('fun-mode').checked?'🏃':''}</p><h2>${esc(r.reportName)}</h2><p class="muted">${esc(dateText(r.createTime))} · ${r.duration} 秒</p><p>有效识别 ${(r.quality.validFrameRatio*100).toFixed(0)}% · ${r.quality.status==='insufficient'?'数据不足':`${r.eventCount} 个回看标记`}</p><div class="report-mini"><div><strong>${valueText(r.metrics.leanAngle)}</strong><span>前倾角度 °</span></div><div><strong>${valueText(r.metrics.verticalOscillation)}</strong><span>垂直振幅 cm</span></div></div></button>`).join('') : '<div class="empty">暂无匹配的报告。完成分析后，报告会自动保存在这里。</div>';
}
function captureSettings() {
  const config={heightCm:Number($('capture-height').value),view:$('capture-view').value,direction:$('capture-direction').value,
    calibrationPixels:$('capture-pixels').value ? Number($('capture-pixels').value):null};
  if(config.heightCm<80 || config.heightCm>240) throw new Error('请输入 80–240 cm 之间的身高');
  if(config.calibrationPixels!==null && (config.calibrationPixels<20 || config.calibrationPixels>5000)) throw new Error('标定高度须在 20–5000 像素之间');
  return config;
}
async function submitVideo(file, reportType='upload') {
  if(!needUser()) return null;
  const config=captureSettings();
  const form=new FormData(); form.append('video',file,file.name || 'camera.webm');
  const uploaded=await api('upload/video',{method:'POST',body:form});
  const job=await api('analyze/video',{method:'POST',body:{videoId:uploaded.videoId,settings:config,reportType}});
  await refresh(); return job;
}
async function chooseFile(file) {
  closeCamera();
  if(!file) return;
  if(file.size>200*1024*1024) throw new Error('视频不能超过 200 MB');
  if(state.fileURL) URL.revokeObjectURL(state.fileURL);
  state.file=file; state.fileURL=URL.createObjectURL(file);
  const preview=$('preview'); preview.srcObject=null; preview.src=state.fileURL; preview.hidden=false; preview.controls=true;
  $('file-label').textContent=`${file.name} · ${(file.size/1024/1024).toFixed(1)} MB`;
  $('capture-pixels').value=''; $('calibration-panel').hidden=true;
  $('quality-result').textContent='可先播放到全身入镜的画面，再检查或标定。';
  preview.load();
  const beginRealtime=()=>{$('preview').play().catch(()=>{}); startPoseAnalysis();};
  if(preview.readyState>=1) beginRealtime(); else preview.addEventListener('loadedmetadata',beginRealtime,{once:true});
}
function currentCanvas() {
  const video=$('preview');
  if(video.readyState<2 || !video.videoWidth) throw new Error('请先选择可播放的视频或打开摄像头，等待画面出现');
  const canvas=document.createElement('canvas'); canvas.width=video.videoWidth; canvas.height=video.videoHeight;
  canvas.getContext('2d').drawImage(video,0,0); return canvas;
}
async function checkQuality() {
  if(!needUser()) return;
  const canvas=currentCanvas(); $('quality-check').disabled=true;
  $('quality-result').textContent='正在检查画面；如已有分析任务，将等待其完成。';
  try {
    const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/jpeg',.85));
    const q=await api(`quality/frame?view=${$('capture-view').value}`,{method:'POST',body:blob});
    $('quality-result').classList.toggle('warning',!q.usable || q.messages.length>0);
    $('quality-result').innerHTML=`<strong>${q.usable?'当前画面可以采集':'建议调整后再采集'}</strong> · 关键点可用比例 ${(q.visibility*100).toFixed(0)}%<ul>${(q.messages.length?q.messages:['全身入镜和亮度检查通过']).map(m=>`<li>${esc(m)}</li>`).join('')}</ul>`;
  } catch(error) { $('quality-result').textContent=error.message; throw error; }
  finally { $('quality-check').disabled=false; }
}
async function openCamera() {
  if(!needUser()) return;
  if(!navigator.mediaDevices?.getUserMedia) throw new Error('摄像头需要 localhost 或 HTTPS 环境');
  closeCamera();
  state.stream=await navigator.mediaDevices.getUserMedia({video:{width:{ideal:1280},height:{ideal:720},facingMode:'environment'},audio:false});
  state.file=null; const preview=$('preview'); preview.removeAttribute('src'); preview.srcObject=state.stream;
  preview.hidden=false; preview.controls=false; await preview.play();
  $('camera-controls').hidden=false; $('camera-close').hidden=false; $('camera-open').hidden=true;
  $('file-label').textContent='摄像头已开启'; $('capture-pixels').value=''; $('calibration-panel').hidden=true;
  $('quality-result').textContent='请站到拍摄位置，点击“检查当前画面”。';
  state.stream.getVideoTracks()[0]?.addEventListener('ended',closeCamera,{once:true});
  startPoseAnalysis();
}
function closeCamera() {
  stopPoseAnalysis(); $('pose-panel').hidden=true;
  state.live=false; state.discardRecording=true;
  if(state.recorder && state.recorder.state!=='inactive') state.recorder.stop();
  state.stream?.getTracks().forEach(track=>track.stop()); state.stream=null; state.recording=false;
  $('preview').srcObject=null; $('camera-controls').hidden=true; $('camera-close').hidden=true; $('camera-open').hidden=false;
  recordingUI(false); if(window.speechSynthesis) speechSynthesis.cancel();
}
function makeRecorder() {
  if(!window.MediaRecorder) throw new Error('当前浏览器不支持视频录制，请上传视频');
  const mime=['video/webm;codecs=vp8','video/webm','video/mp4'].find(type=>MediaRecorder.isTypeSupported(type));
  if(!mime) throw new Error('当前浏览器没有可用的录制格式');
  return new MediaRecorder(state.stream,{mimeType:mime});
}
function recordingUI(active) {
  $('record-start').hidden=active; $('record-pause').hidden=!active || state.live; $('record-stop').hidden=!active;
  $('live-start').hidden=active; $('record-pause').textContent='暂停录制';
  $('analyze-btn').disabled=active; $('video-file').disabled=active;
  if(!active) $('record-status').textContent='';
}
function recordFile(chunks,mime) { return new File(chunks,`摄像头-${new Date().toISOString().replace(/[:.]/g,'-')}.${mime.includes('mp4')?'mp4':'webm'}`,{type:mime}); }
function startRecording() {
  if(!state.stream) throw new Error('请先打开摄像头');
  state.discardRecording=false; state.recording=true;
  const recorder=state.recorder=makeRecorder(), chunks=[];
  recorder.ondataavailable=e=>{if(e.data.size) chunks.push(e.data);};
  const limit=setTimeout(()=>{if(recorder.state!=='inactive') recorder.stop();},600000);
  recorder.onstop=async()=>{
    clearTimeout(limit); state.recording=false; recordingUI(false);
    if(state.discardRecording || !chunks.length) return;
    try { state.file=recordFile(chunks,recorder.mimeType); $('file-label').textContent=state.file.name;
      $('record-status').textContent='正在上传录制内容…'; await submitVideo(state.file,'realtime');
      toast('录制已提交，可在任务区查看进度');
    } catch(error) { toast(error.message+'；录制内容仍可点击开始分析重新提交'); }
    finally { $('record-status').textContent=''; }
  };
  recorder.onerror=e=>toast(e.error?.message || '录制失败');
  recorder.start(1000); recordingUI(true); $('record-status').textContent='正在录制（最长 10 分钟）';
}
async function liveAnalysis() {
  if(!state.stream) throw new Error('请先打开摄像头');
  captureSettings(); state.live=true; state.discardRecording=false; recordingUI(true);
  $('live-feedback').hidden=false; $('live-feedback').textContent='每段录制约 3 秒，完成分析后开始下一段。';
  try {
    while(state.live && state.stream) {
      $('record-status').textContent='正在录制 3 秒片段…';
      const recorder=state.recorder=makeRecorder(), chunks=[];
      const blob=await new Promise((resolve,reject)=>{
        recorder.ondataavailable=e=>{if(e.data.size) chunks.push(e.data);};
        recorder.onerror=e=>reject(e.error || new Error('录制失败'));
        const timer=setTimeout(()=>{if(recorder.state!=='inactive') recorder.stop();},3000);
        recorder.onstop=()=>{clearTimeout(timer);resolve(recordFile(chunks,recorder.mimeType));}; recorder.start();
      });
      if(!state.live || !blob.size) break;
      $('record-status').textContent='上传并等待分析…';
      const job=await submitVideo(blob,'realtime');
      let finished;
      while(state.live) {
        finished=await api(`analysis/${job.analysisId}`);
        if(['completed','failed'].includes(finished.status)) break;
        await new Promise(resolve=>setTimeout(resolve,1000));
      }
      if(!state.live) break;
      if(finished.status==='failed') throw new Error(finished.error);
      const report=await api(`report/${finished.reportId}`);
      const text=report.quality.status==='insufficient'?'当前片段识别不足，请调整拍摄位置。':
        `前倾 ${valueText(report.metrics.leanAngle)} 度，垂直振幅 ${valueText(report.metrics.verticalOscillation)} 厘米。${report.events.length?'有参考阈值偏离，请回看报告。':'本片段分析完成。'}`;
      $('live-feedback').textContent=text;
      if($('voice-enabled').checked && window.speechSynthesis) { speechSynthesis.cancel(); const speech=new SpeechSynthesisUtterance(text); speech.lang='zh-CN'; speechSynthesis.speak(speech); }
      await refresh();
    }
  } finally { state.live=false; recordingUI(false); }
}

function chart(container, series, {duration=1, label='', normalized=false, selected=null, onSeek=null, tickLabels=null}={}) {
  const width=640,height=250,left=52,right=18,top=20,bottom=40,pw=width-left-right,ph=height-top-bottom;
  const values=series.flatMap(s=>s.points.map(p=>p.y)).filter(finite);
  if(!values.length) { container.innerHTML='<div class="empty">当前指标没有足够的有效数据。</div>'; return; }
  let low=Math.min(...values),high=Math.max(...values); const pad=Math.max((high-low)*.15,1); low-=pad;high+=pad;
  const x=t=>left+Math.max(0,Math.min(1,t/Math.max(duration,.001)))*pw;
  const y=v=>top+ph-(v-low)/(high-low)*ph;
  let svg=`<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(label)}变化曲线" class="${onSeek?'interactive':''}">`;
  for(let i=0;i<5;i++) { const v=low+(high-low)*i/4,yy=y(v); svg+=`<line x1="${left}" x2="${width-right}" y1="${yy}" y2="${yy}" stroke="#e7ece8"/><text x="${left-8}" y="${yy+4}" text-anchor="end" fill="#7b8d83" font-size="11">${v.toFixed(1)}</text>`; }
  for(let i=0;i<=4;i++) { const xx=x(duration*i/4); const text=tickLabels ? tickLabels[Math.round((tickLabels.length-1)*i/4)] : `${(duration*i/4).toFixed(normalized?0:1)}${normalized?'%':'s'}`; svg+=`<text x="${xx}" y="${height-13}" text-anchor="middle" fill="#7b8d83" font-size="11">${esc(text)}</text>`; }
  for(const s of series) { let path='',connected=false; for(const p of s.points) { if(!finite(p.y)) { connected=false;continue; } path+=`${connected?'L':'M'}${x(p.x).toFixed(2)},${y(p.y).toFixed(2)} `; connected=true; } svg+=`<path d="${path}" fill="none" stroke="${s.color}" stroke-width="2"/>`; if(s.points.filter(p=>finite(p.y)).length===1) {const p=s.points.find(p=>finite(p.y));svg+=`<circle cx="${x(p.x)}" cy="${y(p.y)}" r="4" fill="${s.color}"/>`;} }
  svg+=`<line class="play-cursor" x1="${x(selected||0)}" x2="${x(selected||0)}" y1="${top}" y2="${top+ph}" stroke="#d39947" stroke-width="1.5" stroke-dasharray="4 3"/></svg>`;
  container.innerHTML=svg;
  if(onSeek) container.querySelector('svg').onclick=e=>{ const rect=e.currentTarget.getBoundingClientRect();onSeek(Math.max(0,Math.min(duration,((e.clientX-rect.left)/rect.width*width-left)/pw*duration))); };
}
function setCursor(container,time,duration) { const line=container.querySelector('.play-cursor'); if(line) {const x=52+Math.max(0,Math.min(1,time/Math.max(.001,duration)))*570;line.setAttribute('x1',x);line.setAttribute('x2',x);} }
async function openReport(id) {
  if(!needUser()) return;
  const report=await api(`report/${id}`); state.report=report;
  $('detail-title').textContent=report.reportName;
  $('detail-meta').textContent=`${dateText(report.createTime)} · ${report.duration} 秒 · ${report.width} × ${report.height}`;
  const q=report.quality;
  $('detail-quality').classList.toggle('warning',q.status==='insufficient');
  $('detail-quality').textContent=`${q.status==='insufficient'?'无法评估':'全片有效数据汇总'} · 有效识别 ${(q.validFrameRatio*100).toFixed(0)}%（${q.validFrames}/${q.totalFrames} 帧）。${q.note}`;
  $('detail-metrics').innerHTML=['leanAngle','verticalOscillation','cadence','leftKnee'].map(key=>`<div class="metric"><span>${metrics[key][0]}</span><strong>${valueText(report.metrics[key])}<small>${finite(report.metrics[key])?metrics[key][1]:''}</small></strong></div>`).join('');
  for(const kind of ['pdf','csv']) $('export-'+kind).href=apiURL(`report/${id}/export/${kind}`);
  $('export-video').href=apiURL(`report/${id}/media?download=1`);
  $('report-video').src=mediaURL(report.videoUrl); $('report-video').playbackRate=Number($('playback-speed').value);
  $('timeline').max=report.duration; $('timeline').value=0;
  $('detail-suggestions').innerHTML=report.suggestions.map(s=>`<p>${esc(s)}</p>`).join('');
  $('detail-settings').innerHTML=`<p>身高 ${report.settings.heightCm} cm · ${report.settings.view==='side'?'侧面':'正面'} · 朝${report.settings.direction==='right'?'右':'左'} · ${esc(q.scaleMethod)}</p>${q.issues.map(i=>`<p>${esc(i.message)}：${i.frames} 帧</p>`).join('')}<p>脚相对髋部距离是有正负号的水平位置，不等同于落地步长；关节角度为三点夹角。</p>`;
  $('detail-events').innerHTML=report.events.length?report.events.map(e=>`<button data-time="${e.time}">${e.time.toFixed(1)}s · ${esc(e.issues.join('、'))}</button>`).join(''):'<p class="muted small">当前报告没有可用的异常标记。</p>';
  renderDetailChart(); updatePlayback(); page('detail'); window.scrollTo({top:0,behavior:'smooth'});
}
function renderDetailChart() { if(!state.report) return; const key=$('detail-metric').value,r=state.report;chart($('detail-chart'),[{color:'#276c50',points:r.timeSeries.map(p=>({x:p.time,y:p[key]}))}],{duration:r.duration,label:metrics[key][0],selected:$('report-video').currentTime,onSeek:seekReport}); }
function seekReport(time) { $('report-video').currentTime=time; updatePlayback(); }
function updatePlayback() {
  const r=state.report;if(!r)return;const time=$('report-video').currentTime || 0;
  $('timeline').value=time; $('playback-time').textContent=`${time.toFixed(1)} / ${r.duration.toFixed(1)} 秒`; setCursor($('detail-chart'),time,r.duration);
  const row=r.timeSeries.reduce((best,p)=>!best||Math.abs(p.time-time)<Math.abs(best.time-time)?p:best,null);
  $('current-joints').innerHTML=['leftKnee','rightKnee','leftHip','rightHip','leftAnkle','rightAnkle'].map(key=>`<span>${metrics[key][0]}：${valueText(row?.[key])}${finite(row?.[key])?'°':''}</span>`).join('');
}
function populateCompare() {
  for(const id of ['compare-a','compare-b']) {const previous=$(id).value;$(id).innerHTML=state.reports.map(r=>`<option value="${r.reportId}">${esc(r.reportName)} · ${esc(dateText(r.createTime))}</option>`).join(''); if(state.reports.some(r=>r.reportId===previous)) $(id).value=previous;}
  if($('compare-a').value===$('compare-b').value && state.reports.length>1) $('compare-b').selectedIndex=1;
}
async function compare() {
  if(!needUser())return;
  const a=$('compare-a').value,b=$('compare-b').value;
  if(!a||!b||a===b)throw new Error('请选择两份不同的报告');
  state.pair=await Promise.all([api(`report/${a}`),api(`report/${b}`)]);
  const [ra,rb]=state.pair;$('comparison').hidden=false;
  $('compare-title-a').textContent='A · '+ra.reportName;$('compare-title-b').textContent='B · '+rb.reportName;
  $('compare-video-a').src=mediaURL(ra.videoUrl);$('compare-video-b').src=mediaURL(rb.videoUrl);
  const different=['heightCm','view','direction'].some(k=>ra.settings[k]!==rb.settings[k]) || ra.quality.scaleMethod!==rb.quality.scaleMethod;
  $('compare-warning').classList.toggle('warning',different);
  $('compare-warning').textContent=different?'两次采集的身高、视角、方向或标定方法不同，差值只作观察，请优先比较同条件视频。':'采集参数一致。不同速度、镜头距离和标定误差仍可能影响差值。';
  $('compare-table').innerHTML='<thead><tr><th>指标</th><th>训练 A</th><th>训练 B</th><th>B − A</th></tr></thead><tbody>'+Object.entries(metrics).map(([key,[label,unit]])=>{const x=ra.metrics[key],y=rb.metrics[key];return `<tr><td>${label}（${unit}）</td><td>${valueText(x)}</td><td>${valueText(y)}</td><td>${finite(x)&&finite(y)?`${y-x>0?'+':''}${(y-x).toFixed(1)}`:'无法比较'}</td></tr>`;}).join('')+'</tbody>';
  renderCompareChart();
}
function seekPair(percent) { if(!state.pair)return; ['a','b'].forEach((key,i)=>{$('compare-video-'+key).currentTime=state.pair[i].duration*percent/100;});$('compare-timeline').value=percent;setCursor($('compare-chart'),percent,100); }
function renderCompareChart() { if(!state.pair)return;const key=$('compare-metric').value;chart($('compare-chart'),state.pair.map((r,i)=>({color:i?'#4278ba':'#276c50',points:r.timeSeries.map(p=>({x:p.time/r.duration*100,y:p[key]}))})),{duration:100,normalized:true,label:metrics[key][0],onSeek:seekPair}); }
function renderGrowth() {
  const key=$('growth-metric').value,reports=[...state.reports].reverse();
  chart($('growth-chart'),[{color:'#276c50',points:reports.map((r,i)=>({x:i,y:r.metrics[key]}))}],{duration:Math.max(1,reports.length-1),label:metrics[key][0],tickLabels:reports.map(r=>new Date(r.createTime).toLocaleDateString('zh-CN')),
    onSeek:index=>{const r=reports[Math.round(index)];if(r)openReport(r.reportId).catch(e=>toast(e.message));}});
  const valid=reports.filter(r=>finite(r.metrics[key]));
  $('growth-summary').textContent=valid.length<2?'至少需要两次可评估的训练，才能比较变化。':`最近两次可评估记录：${valueText(valid.at(-2).metrics[key])} → ${valueText(valid.at(-1).metrics[key])} ${metrics[key][1]}。数值升降不直接代表好坏，请结合视频与采集条件判断。点击趋势图可打开对应报告。`;
}
function editDialog(title,message,value,callback) {
  $('edit-title').textContent=title;$('edit-message').textContent=message;$('edit-value').hidden=value===null;$('edit-value').value=value||'';
  $('edit-form').onsubmit=async e=>{e.preventDefault();$('edit-confirm').disabled=true;try{await callback($('edit-value').value);$('edit-dialog').close();}catch(error){toast(error.message);}finally{$('edit-confirm').disabled=false;}};
  $('edit-dialog').showModal();
}

document.addEventListener('click', e=>{
  const nav=e.target.closest('[data-page]');if(nav){page(nav.dataset.page);return;}
  const report=e.target.closest('[data-report]');if(report)openReport(report.dataset.report).catch(error=>toast(error.message));
  const retry=e.target.closest('[data-retry]');if(retry){retry.disabled=true;api(`analysis/${retry.dataset.retry}/retry`,{method:'POST'}).then(refresh).catch(error=>{toast(error.message);retry.disabled=false;});}
  const event=e.target.closest('[data-time]');if(event)seekReport(Number(event.dataset.time));
});
on('account-btn','click',async()=>{if(state.user){await api('auth/logout',{method:'POST'});resetAccount();}else showAuth();});
on('auth-toggle','click',()=>{state.registering=!state.registering;$('auth-title').textContent=state.registering?'创建你的运动空间':'登录你的运动空间';$('auth-submit').textContent=state.registering?'注册并登录':'登录';$('auth-toggle').textContent=state.registering?'已有账号？登录':'没有账号？注册';$('auth-password').autocomplete=state.registering?'new-password':'current-password';$('auth-error').textContent='';});
on('auth-close','click',()=>$('auth-dialog').close());
on('auth-form','submit',async e=>{e.preventDefault();$('auth-submit').disabled=true;$('auth-error').textContent='';try{const user=await api(`auth/${state.registering?'register':'login'}`,{method:'POST',body:{username:$('auth-username').value.trim(),password:$('auth-password').value}});state.authEpoch++;state.user=user;profileToForms();$('auth-password').value='';$('auth-dialog').close();await refresh();}catch(error){$('auth-error').textContent=error.message;}finally{$('auth-submit').disabled=false;}});
on('profile-form','submit',async e=>{e.preventDefault();if(!needUser())return;const p={nickname:$('profile-nickname').value,heightCm:Number($('profile-height').value),age:$('profile-age').value,gender:$('profile-gender').value,view:$('profile-view').value,direction:$('profile-direction').value,calibrationPixels:null};state.user.profile=await api('profile',{method:'PUT',body:p});profileToForms();toast('资料已保存');});
on('video-file','change',e=>chooseFile(e.target.files[0]));
on('analyze-btn','click',async()=>{if(!needUser()||state.busy)return;if(!state.file)throw new Error('请先选择视频，或使用摄像头录制');state.busy=true;$('analyze-btn').disabled=true;$('analyze-btn').textContent='正在上传并创建任务…';try{await submitVideo(state.file);toast('任务已提交，关闭页面后仍会继续分析');}finally{state.busy=false;$('analyze-btn').disabled=false;$('analyze-btn').textContent='开始分析';}});
on('camera-open','click',openCamera);on('camera-close','click',closeCamera);on('quality-check','click',checkQuality);
on('record-start','click',startRecording);on('live-start','click',liveAnalysis);
on('record-pause','click',()=>{const r=state.recorder;if(r?.state==='recording'){r.pause();$('record-pause').textContent='继续录制';$('record-status').textContent='录制已暂停';}else if(r?.state==='paused'){r.resume();$('record-pause').textContent='暂停录制';$('record-status').textContent='正在录制';}});
on('record-stop','click',()=>{state.live=false;if(state.recorder?.state!=='inactive')state.recorder?.stop();recordingUI(false);});
on('calibrate','click',()=>{const src=currentCanvas(),canvas=$('calibration-canvas');canvas.width=src.width;canvas.height=src.height;canvas.getContext('2d').drawImage(src,0,0);state.calibration=[];$('calibration-panel').hidden=false;$('calibration-hint').textContent='点击站直人体的头顶，再点击脚底。也可直接填写身高对应像素。';});
on('calibration-canvas','click',e=>{if(state.calibration.length===2)return;const canvas=e.currentTarget,rect=canvas.getBoundingClientRect(),y=(e.clientY-rect.top)/rect.height*canvas.height;state.calibration.push(y);const ctx=canvas.getContext('2d');ctx.strokeStyle='#e9a943';ctx.lineWidth=3;ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(canvas.width,y);ctx.stroke();if(state.calibration.length===2){const height=Math.abs(state.calibration[1]-state.calibration[0]);if(height<20)throw new Error('两点太近，请重新标定');$('capture-pixels').value=Math.round(height);$('calibration-hint').textContent=`标定完成：${Math.round(height)} 像素。更换视频或移动机位后请重新标定。`;}else $('calibration-hint').textContent='接下来点击同一人的脚底。';});
on('calibration-clear','click',()=>{$('capture-pixels').value='';$('calibration-panel').hidden=true;});
on('refresh-jobs','click',refresh);on('refresh-reports','click',refresh);on('report-search','input',renderReports);
on('detail-metric','change',renderDetailChart);on('timeline','input',e=>seekReport(Number(e.target.value)));on('report-video','timeupdate',updatePlayback);
on('playback-speed','change',e=>{$('report-video').playbackRate=Number(e.target.value);});
on('rename-report','click',()=>{if(!state.report)return;editDialog('重命名报告','名称会同步保存在账号中。',state.report.reportName,async name=>{await api(`report/${state.report.reportId}/name`,{method:'PUT',body:{reportName:name}});await openReport(state.report.reportId);await refresh();});});
on('delete-report','click',()=>{if(!state.report)return;editDialog('删除报告','此报告及其骨架视频将被删除。',null,async()=>{await api(`report/${state.report.reportId}`,{method:'DELETE'});state.report=null;await refresh();page('reports');});});
on('edit-cancel','click',()=>$('edit-dialog').close());
on('compare-btn','click',compare);on('compare-metric','change',renderCompareChart);on('compare-timeline','input',e=>seekPair(Number(e.target.value)));
on('compare-play','click',async()=>{const a=$('compare-video-a'),b=$('compare-video-b');if(a.paused){if(a.ended)seekPair(0);await Promise.all([a.play(),b.play()]);}else{a.pause();b.pause();}});
on('compare-video-a','timeupdate',()=>{if(!state.pair)return;const a=$('compare-video-a'),b=$('compare-video-b'),percent=a.currentTime/state.pair[0].duration*100;$('compare-timeline').value=percent;setCursor($('compare-chart'),percent,100);if($('compare-sync').checked){const target=percent/100*state.pair[1].duration;if(Math.abs(b.currentTime-target)>.25)b.currentTime=target;b.playbackRate=Math.max(.25,Math.min(4,state.pair[1].duration/state.pair[0].duration));}});
on('growth-metric','change',renderGrowth);
on('voice-enabled','change',()=>{localStorage.setItem('posepro_voice',String($('voice-enabled').checked));if(!$('voice-enabled').checked)window.speechSynthesis?.cancel();});
on('fun-mode','change',()=>{localStorage.setItem('posepro_fun',String($('fun-mode').checked));document.body.classList.toggle('fun',$('fun-mode').checked);renderReports();});
on('legacy-export','click',()=>{const blob=new Blob([localStorage.getItem('kinetix_reports')||'[]'],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='posepro-legacy-records.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
window.addEventListener('beforeunload',closeCamera);
for(const id of ['detail-metric','compare-metric','growth-metric'])$(id).innerHTML=Object.entries(metrics).filter(([key])=>id==='growth-metric'||key!=='cadence').map(([key,[label,unit]])=>`<option value="${key}">${label}（${unit}）</option>`).join('');
$('voice-enabled').checked=localStorage.getItem('posepro_voice')!=='false';$('fun-mode').checked=localStorage.getItem('posepro_fun')==='true';document.body.classList.toggle('fun',$('fun-mode').checked);
$('legacy-export').hidden=!localStorage.getItem('kinetix_reports');
(async()=>{try{state.user=await api('auth/me');profileToForms();await refresh();}catch(error){if(!state.user)showAuth();else toast(error.message);}state.polling=setInterval(()=>{if(state.user)refresh().catch(error=>{console.warn(error.message);});},2500);})();

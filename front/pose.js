'use strict';
const poseState = {socket:null, timer:null, watchdog:null, generation:0, frames:0};
const liveBuffer = {rows:[], samples:[], frames:0, usable:0, issues:{}, width:0, height:0, lastTime:0, frameScale:1, detected:null};
let liveRec = null, liveClip = null;
function resetLiveBuffer() {
  liveBuffer.rows=[]; liveBuffer.samples=[]; liveBuffer.frames=0; liveBuffer.usable=0; liveBuffer.issues={};
  liveBuffer.width=0; liveBuffer.height=0; liveBuffer.lastTime=0; liveBuffer.detected=null;
}
function collectLiveFrame(data) {
  liveBuffer.frames++;
  if(data.quality?.usable) liveBuffer.usable++;
  for(const message of data.quality?.messages||[]) liveBuffer.issues[message]=(liveBuffer.issues[message]||0)+1;
  if(data.width) liveBuffer.width=data.width;
  if(data.height) liveBuffer.height=data.height;
  if(data.detected) liveBuffer.detected=data.detected;
  const time=Number(data.metrics?.time)||0;
  liveBuffer.lastTime=Math.max(liveBuffer.lastTime, time);
  if(liveBuffer.rows.length<20000) liveBuffer.rows.push({...data.metrics, visibility:data.quality?.visibility});
  if(liveBuffer.samples.length<20000) {
    const angle=value=>finite(value)?Math.round(value*10)/10:null;
    liveBuffer.samples.push({t:time, p:(data.points||[]).flat(), v:data.visibility||[],
      k:[angle(data.metrics?.leftKnee), angle(data.metrics?.rightKnee)]});
  }
}
function liveSnapshot() {
  if(liveBuffer.frames<5 || !liveBuffer.rows.length) return null;
  const config=captureSettings();
  if(config.calibrationPixels) config.calibrationPixels=Math.max(20,Math.round(config.calibrationPixels*liveBuffer.frameScale));
  config.view=liveBuffer.detected?.view || 'auto';
  config.direction=liveBuffer.detected?.direction || 'auto';
  return {rows:liveBuffer.rows, samples:liveBuffer.samples, settings:config, duration:liveBuffer.lastTime,
    width:liveBuffer.width, height:liveBuffer.height,
    quality:{totalFrames:liveBuffer.frames, usableFrames:liveBuffer.usable, issues:liveBuffer.issues}};
}
function startLiveRecording() {
  if(!state.stream || !window.MediaRecorder || liveRec) return;
  const mime=['video/webm;codecs=vp8','video/webm','video/mp4'].find(type=>MediaRecorder.isTypeSupported(type));
  if(!mime) return;
  let recorder;
  try { recorder=new MediaRecorder(state.stream,{mimeType:mime,videoBitsPerSecond:2000000}); }
  catch(error) { console.warn('实时同步录制不可用', error); return; }
  const rec={recorder, chunks:[], blob:null, mime, timer:null, pending:null, discard:false};
  recorder.ondataavailable=e=>{if(e.data.size) rec.chunks.push(e.data);};
  recorder.onstop=()=>{rec.blob=rec.chunks.length?new Blob(rec.chunks,{type:mime}):null;};
  recorder.start(1000);
  rec.timer=setTimeout(()=>{
    if(liveRec===rec) stopPoseAnalysis('已达到 10 分钟录制上限，请保存结果或重新开启实时分析');
  },600000);
  liveRec=rec; $('live-recording').hidden=false;
}
function stopLiveRecording() {
  const rec=liveRec;
  if(!rec) return Promise.resolve(liveClip);
  if(rec.pending) return rec.pending;
  rec.pending=new Promise(resolve=>{
    const finish=()=>{
      clearTimeout(rec.timer); rec.timer=null;
      if(!rec.discard && rec.blob?.size) liveClip=rec.blob;
      if(liveRec===rec) liveRec=null;
      $('live-recording').hidden=true;
      resolve(liveClip);
    };
    if(rec.recorder.state==='inactive') {finish();return;}
    rec.recorder.addEventListener('stop',finish,{once:true});
    try {rec.recorder.stop();} catch(error) {finish();}
  });
  return rec.pending;
}
function discardLiveClip() {
  if(liveRec) liveRec.discard=true;
  stopLiveRecording();
  liveClip=null;
}
function clearLiveClip() { liveClip=null; }
function stopPoseAnalysis(message='实时分析已停止') {
  poseState.generation++; clearTimeout(poseState.timer); clearTimeout(poseState.watchdog);
  const socket=poseState.socket; poseState.socket=null; socket?.close();
  $('pose-overlay').hidden=true; $('pose-status').textContent=message;
  $('pose-metrics').replaceChildren(); $('pose-hint').textContent='';
  $('pose-toggle').textContent='开始实时分析';
  stopLiveRecording();
}
function drawPose(data) {
  const canvas=$('pose-overlay'), ctx=canvas.getContext('2d');
  canvas.width=data.width; canvas.height=data.height; canvas.hidden=false;
  ctx.clearRect(0,0,canvas.width,canvas.height);
  const visible=i=>data.visibility[i]>=.6 && data.points[i]?.every(Number.isFinite);
  ctx.strokeStyle='#65ffad'; ctx.fillStyle='#fff'; ctx.lineWidth=3;
  for(const [a,b] of data.edges) if(visible(a)&&visible(b)) {
    ctx.beginPath();ctx.moveTo(data.points[a][0]*canvas.width,data.points[a][1]*canvas.height);
    ctx.lineTo(data.points[b][0]*canvas.width,data.points[b][1]*canvas.height);ctx.stroke();
  }
  data.points.forEach((p,i)=>{if(visible(i)){ctx.beginPath();ctx.arc(p[0]*canvas.width,p[1]*canvas.height,3,0,Math.PI*2);ctx.fill();}});
  const d=data.detected||{}, parts=[];
  if(d.autoView && d.view) parts.push(d.view==='side'?'侧面':'正面');
  if(d.autoDirection && d.direction) parts.push('朝'+(d.direction==='right'?'右':'左'));
  $('pose-status').textContent=`${data.points.length?'正在识别':'等待人体入镜'} · 关键点可用 ${(data.quality.visibility*100).toFixed(0)}%${parts.length?` · 自动判断：${parts.join('、')}`:''}`;
  $('pose-metrics').innerHTML=['leanAngle','verticalOscillation','leftKnee','rightKnee','leftHip','rightHip'].map(key=>`<div><span>${metrics[key][0]}</span><strong>${valueText(data.metrics[key])} <small>${metrics[key][1]}</small></strong></div>`).join('');
  $('pose-hint').textContent=data.quality.messages.join('；') || '请保持全身入镜和固定机位。实时结果仅用于动作观察。';
  collectLiveFrame(data);
  poseState.frames++;
}
function startPoseAnalysis() {
  if(state.mode!=='realtime') return;
  if((!state.stream && !state.fileURL) || !state.user) return;
  const config=captureSettings(); stopPoseAnalysis(); discardLiveClip();
  const preview=$('preview');
  config.frameScale=Math.min(1,960/preview.videoWidth,540/preview.videoHeight);
  resetLiveBuffer(); liveBuffer.frameScale=config.frameScale;
  const generation=poseState.generation;
  $('pose-panel').hidden=false; $('pose-status').textContent='正在连接实时分析…';
  $('pose-toggle').textContent='停止实时分析'; poseState.frames=0;
  const url=new URL(apiURL('realtime/pose'));url.protocol=url.protocol==='https:'?'wss:':'ws:';
  const socket=poseState.socket=new WebSocket(url);
  const active=()=>poseState.socket===socket && poseState.generation===generation && (!!state.stream || !!state.fileURL);
  const armTimeout=()=>{clearTimeout(poseState.watchdog);poseState.watchdog=setTimeout(()=>{if(active())stopPoseAnalysis('实时分析响应超时，请重新开启');},30000);};
  async function sendFrame() {
    if(!active() || socket.readyState!==WebSocket.OPEN) return;
    try {
      const video=$('preview'); if(video.readyState<2) {if(state.fileURL&&video.paused) video.play().catch(()=>{}); poseState.timer=setTimeout(sendFrame,100);return;}
      const canvas=document.createElement('canvas'), ratio=Math.min(1,960/video.videoWidth,540/video.videoHeight);
      canvas.width=Math.max(2,Math.round(video.videoWidth*ratio));canvas.height=Math.max(2,Math.round(video.videoHeight*ratio));
      canvas.getContext('2d').drawImage(video,0,0,canvas.width,canvas.height);
      const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/jpeg',.75));
      if(active() && socket.readyState===WebSocket.OPEN) {if(!blob)throw new Error('无法读取画面');socket.send(blob);armTimeout();}
    } catch(error) {if(active())stopPoseAnalysis(error.message);}
  }
  socket.onopen=()=>{if(active()){socket.send(JSON.stringify(config));armTimeout();}};
  socket.onmessage=event=>{
    if(!active()) return;
    clearTimeout(poseState.watchdog);
    try {
      const data=JSON.parse(event.data);
      if(data.type==='error') {stopPoseAnalysis(data.message);return;}
      if(data.type==='frame') drawPose(data);
      if(data.type==='ready') startLiveRecording();
      if(data.type==='ready'||data.type==='frame') poseState.timer=setTimeout(sendFrame,data.type==='ready'?0:100);
    } catch(error) {stopPoseAnalysis('实时分析数据异常，请重新开启');}
  };
  socket.onerror=()=>{if(active())stopPoseAnalysis('实时分析连接失败，请确认已登录且服务可用');};
  socket.onclose=()=>{if(active())stopPoseAnalysis('实时分析连接已断开，点击重新开启');};
}
on('pose-toggle','click',()=>{if(poseState.socket)stopPoseAnalysis();else startPoseAnalysis();});
for(const id of ['capture-height','capture-view','capture-direction','capture-pixels']) on(id,'change',()=>{if(poseState.socket)startPoseAnalysis();});
on('calibration-canvas','click',()=>{if(state.calibration.length===2 && poseState.socket)startPoseAnalysis();});
on('calibration-clear','click',()=>{if(poseState.socket)startPoseAnalysis();});

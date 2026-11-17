/* Static recorded-run explorer. No network requests, inference or dependencies. */
(() => {
  'use strict';
  const data = window.STRONGARM_EXPERIMENT;
  const $ = id => document.getElementById(id);
  if (!data || data.schema !== 1 || !data.waveforms?.points?.length) {
    $('data-error').hidden = false;
    $('data-error').textContent = 'The recorded dataset could not be loaded. Keep the assets folder alongside this page.';
    return;
  }
  const points = data.waveforms.points;
  const count = data.choices.length;
  const period = 1000 / data.clock_MHz;
  const colors = {green:'#18645d', orange:'#c46a35', purple:'#786a9c', clock:'#7b8483', ink:'#182d2b', muted:'#5e6c69', grid:'#e8ede7'};
  let selected = 0;
  let view = 'run';
  let waveGeometry;
  let stemGeometry;
  let pendingDraw = false;

  const number = (value, digits=6) => Number(value.toFixed(digits)).toString().replace('-', '−');
  const signed = value => (value > 0 ? '+' : '') + number(value);
  const setText = (id, value) => { $(id).textContent = value; };
  const buttons = [];

  for (let i=0; i<=count; i++) {
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = i === count ? 'Stop' : String(i+1).padStart(2, '0');
    button.setAttribute('aria-label', i === count ? 'Model call 13: stop' : `Experiment ${i+1}: ${signed(data.choices[i].response.diff_mV)} millivolts`);
    button.addEventListener('click', () => select(i));
    $('decision-buttons').append(button);
    buttons.push(button);
  }
  $('previous').addEventListener('click', () => select(selected-1));
  $('next').addEventListener('click', () => select(selected+1));
  document.querySelectorAll('[data-view]').forEach(button => {
    button.addEventListener('click', () => {
      view = button.dataset.view;
      document.querySelectorAll('[data-view]').forEach(b => b.setAttribute('aria-pressed', String(b === button)));
      updateCaption();
      scheduleDraw();
    });
  });
  $('show-recheck').addEventListener('click', () => select(count-1));
  $('download-data').addEventListener('click', () => {
    const url = URL.createObjectURL(new Blob([JSON.stringify(data)], {type:'application/json'}));
    const link = document.createElement('a');
    link.href = url;
    link.download = 'strongarm-recorded-experiment.json';
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });

  function addMetric(label, value) {
    const row = document.createElement('div');
    const term = document.createElement('dt');
    const description = document.createElement('dd');
    term.textContent = label;
    description.textContent = value;
    row.append(term, description);
    $('outcome-metrics').append(row);
  }

  function select(index) {
    selected = Math.max(0, Math.min(count, index));
    const stopping = selected === count;
    const choice = data.choices[Math.min(selected, count-1)];
    const response = stopping ? data.final_response : choice.response;
    buttons.forEach((b,i) => b.setAttribute('aria-pressed', String(i === selected)));
    $('previous').disabled = selected === 0;
    $('next').disabled = stopping;
    setText('call-number', `MODEL CALL ${String(selected+1).padStart(2,'0')} / ${data.model_calls}`);
    setText('response-heading', stopping ? 'Stop the experiment' : selected === 0 ? 'Choose the first input' : `Choose input for experiment ${selected+1}`);
    $('chosen-value').replaceChildren(document.createTextNode(stopping ? 'Stop' : signed(response.diff_mV)+' '));
    if (!stopping) {
      const unit = document.createElement('span'); unit.textContent = 'mV'; $('chosen-value').append(unit);
    }
    setText('paused-time', `${number(stopping ? data.duration_ns : choice.time_ns)} ns`);
    setText('inference-time', `${(stopping ? data.final_inference_seconds : choice.inference_seconds).toFixed(2)} s`);
    setText('model-explanation', response.explanation);
    setText('expected-observation', response.expected_observation);
    setText('evidence-used', response.evidence_epochs.length ? `Completed experiment${response.evidence_epochs.length>1?'s':''} ${response.evidence_epochs.join(', ')}. Only observations available before this choice were supplied.` : 'No previous trials. The model has the circuit description and input limits.');
    setText('raw-response', JSON.stringify(response, null, 2));
    setText('outcome-label', stopping ? 'AFTER THIS MODEL CALL' : 'AFTER THIS EXPERIMENT');
    $('outcome-metrics').replaceChildren();
    if (stopping) {
      setText('outcome-title', 'No new stimulus. Simulation stays parked.');
      addMetric('Completed experiments', String(count));
      addMetric('Replay', `${data.replay.identical_points.toLocaleString('en-US')} identical samples`);
    } else {
      const observation = choice.observation;
      setText('outcome-title', `${observation.decision === 1 ? 'OUTP' : 'OUTN'} wins · decision ${observation.decision}`);
      addMetric('OUTP / OUTN', `${number(observation.outp_V,4)} / ${number(observation.outn_V,4)} V`);
      addMetric('Decision delay', `${number(observation.decision_delay_s*1e9,3)} ns`);
      addMetric('Measurement window', observation.hold_window_s.map(t => number(t*1e9,2)).join('–')+' ns');
      addMetric('Precharge minimum', `${number(observation.reset_min_V,4)} V`);
    }
    let low = -Infinity, high = Infinity;
    data.choices.slice(0, Math.min(selected+1,count)).forEach(c => {
      if (c.observation.status !== 'resolved') return;
      if (c.observation.decision === 0) low = Math.max(low, c.response.diff_mV);
      else high = Math.min(high, c.response.diff_mV);
    });
    const bracketed = Number.isFinite(low) && Number.isFinite(high);
    setText('bracket-value', bracketed ? `${number(low)} to ${number(high)} mV` : 'Not established yet');
    setText('bracket-width', bracketed ? `Width ${number(high-low)} mV · from measured polarities` : 'Two opposite, resolved decisions are needed.');
    setText('selection-announcement', stopping ? 'Final model response: stop.' : `Experiment ${selected+1}, ${signed(response.diff_mV)} millivolts. ${choice.observation.decision === 1 ? 'OUTP' : 'OUTN'} wins.`);
    $('wave-cursor').hidden = true;
    $('stem-cursor').hidden = true;
    updateCaption();
    scheduleDraw();
  }

  function range() {
    const start = data.choices[Math.min(selected,count-1)].time_ns;
    if (view === 'cycle') return [start, start+period];
    if (view === 'edge') return [start+9.8, start+11.5];
    return [0, data.duration_ns];
  }
  function updateCaption() {
    const [start,end] = range();
    const stopped = selected === count;
    const label = view === 'run' ? 'entire run' : view === 'cycle' ? 'one cycle' : 'clock rise and regeneration';
    setText('wave-range', `${number(start,2)}–${number(end,2)} ns · ${label}`);
    setText('wave-caption', stopped ? 'The final call stops at 240 ns and applies no new stimulus. The last completed cycle remains highlighted.' : view === 'edge' ? 'The 100 ps clock rise begins 10 ns into the cycle. Delay is measured from its 50% crossing to a sustained valid output decision.' : 'The highlighted interval is the selected experiment. Clock low resets both outputs high; clock high lets the latch decide.');
    $('waveforms').setAttribute('aria-label', `Recorded clock, OUTP, OUTN and external input from ${number(start)} to ${number(end)} nanoseconds. ${stopped?'Final stop call selected.':`Experiment ${selected+1} selected; ${signed(data.choices[selected].response.diff_mV)} millivolts, decision ${data.choices[selected].observation.decision}.`} Numerical results follow the plots.`);
  }
  function scheduleDraw() {
    if (pendingDraw) return;
    pendingDraw = true;
    requestAnimationFrame(() => { pendingDraw = false; drawWaves(); drawStems(); });
  }
  function canvasContext(id) {
    const canvas = $(id);
    const {width,height} = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.round(width*dpr);
    canvas.height = Math.round(height*dpr);
    const ctx = canvas.getContext('2d');
    ctx.setTransform(dpr,0,0,dpr,0,0);
    ctx.font = '11px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
    ctx.lineWidth = 1;
    return {ctx,width,height};
  }
  function line(ctx,x1,y1,x2,y2,color) {
    ctx.strokeStyle = color;
    ctx.beginPath(); ctx.moveTo(x1,y1); ctx.lineTo(x2,y2); ctx.stroke();
  }
  function label(ctx,text,x,y,color=colors.muted,align='left') {
    ctx.fillStyle = color; ctx.textAlign = align; ctx.fillText(text,x,y);
  }
  function lowerBound(time) {
    let lo=0, hi=points.length;
    while (lo<hi) { const mid=(lo+hi)>>>1; if(points[mid][0]<time) lo=mid+1; else hi=mid; }
    return lo;
  }
  // Retain first/last and both extrema in each pixel, in original time order.
  // Striding or averaging would hide the narrow reset and regeneration events.
  function trace(ctx,column,startIndex,endIndex,x,y,color) {
    ctx.strokeStyle=color; ctx.lineWidth=1.4; ctx.beginPath();
    let bucket=-Infinity, first=-1,last=-1,min=-1,max=-1,started=false;
    const flush=() => {
      if (first<0) return;
      for(const i of [...new Set([first,min,max,last])].sort((a,b)=>a-b)) {
        const p=points[i];
        if(started) ctx.lineTo(x(p[0]),y(p[column])); else {ctx.moveTo(x(p[0]),y(p[column])); started=true;}
      }
    };
    for(let i=startIndex;i<endIndex;i++) {
      const pixel=Math.floor(x(points[i][0]));
      if(pixel!==bucket) {flush(); bucket=pixel; first=i; min=i; max=i;}
      last=i;
      if(points[i][column]<points[min][column]) min=i;
      if(points[i][column]>points[max][column]) max=i;
    }
    flush(); ctx.stroke(); ctx.lineWidth=1;
  }

  function drawWaves() {
    const {ctx,width,height} = canvasContext('waveforms');
    if(width<1) return;
    const left=43,right=width-13;
    const [start,end]=range();
    const x=t=>left+(t-start)/(end-start)*(right-left);
    waveGeometry={left,right,start,end,x};
    const chosen=data.choices[Math.min(selected,count-1)];
    const lanes=[
      {top:24,bottom:77,min:-.1,max:1.95,title:'CLOCK · V',ticks:[0,1.8],columns:[1],colors:[colors.clock]},
      {top:117,bottom:225,min:-.12,max:2.05,title:'OUTPUTS · V',ticks:[0,.9,1.8],columns:[2,3],colors:[colors.green,'rgba(196,106,53,0.6)']}, // OUTN: 40% transparency.
      {top:265,bottom:315,min:-112,max:112,title:'EXTERNAL ΔV · mV',ticks:[-100,0,100],columns:[4],colors:[colors.purple]}
    ];
    ctx.fillStyle='#e8f0e9';
    const a=Math.max(left,x(chosen.time_ns)),b=Math.min(right,x(chosen.time_ns+period));
    if(b>a) ctx.fillRect(a,16,b-a,304);
    const tickCount=width<400?4:6;
    for(let i=0;i<=tickCount;i++) {
      const t=start+(end-start)*i/tickCount;
      line(ctx,x(t),18,x(t),320,colors.grid);
      label(ctx,number(t,view==='edge'?2:1),x(t),height-13,colors.muted,i===0?'left':i===tickCount?'right':'center');
    }
    label(ctx,'Time · ns',right,height-1,colors.muted,'right');
    const first=Math.max(0,lowerBound(start)-1),last=Math.min(points.length,lowerBound(end)+1);
    for(const lane of lanes) {
      const y=v=>lane.bottom-(v-lane.min)/(lane.max-lane.min)*(lane.bottom-lane.top);
      label(ctx,lane.title,left,lane.top-9,colors.muted);
      for(const tick of lane.ticks) {
        line(ctx,left,y(tick),right,y(tick),colors.grid);
        label(ctx,number(tick),left-8,y(tick)+3,colors.muted,'right');
      }
      ctx.save(); ctx.beginPath();ctx.rect(left,lane.top,right-left,lane.bottom-lane.top);ctx.clip();
      lane.columns.forEach((col,i)=>trace(ctx,col,first,last,x,y,lane.colors[i]));
      ctx.restore();
    }
    if(view==='run') {
      line(ctx,x(chosen.time_ns),17,x(chosen.time_ns),320,'#9db8a2');
      label(ctx,`#${chosen.number}`,Math.min(right-22,Math.max(left+3,a+4)),13,colors.green);
    }
  }

  function drawStems() {
    const {ctx,width,height}=canvasContext('stems');
    if(width<1) return;
    const left=43,right=width-13,top=24,bottom=height-42;
    const x=t=>left+(t+8)/(data.duration_ns+16)*(right-left);
    const y=v=>bottom-(v+112)/224*(bottom-top);
    stemGeometry={x,y,left,right};
    for(const value of [-100,-50,0,50,100]) {
      line(ctx,left,y(value),right,y(value),value===0?'#bbc8bb':colors.grid);
      label(ctx,number(value),left-8,y(value)+3,colors.muted,'right');
    }
    label(ctx,'ΔV · mV',left,12);
    ctx.setLineDash([4,4]);
    line(ctx,left,y(-data.fixed_offset_mV),right,y(-data.fixed_offset_mV),'#8a9b86');
    ctx.setLineDash([]);
    label(ctx,'−43 mV cancellation',right,bottom+17,colors.muted,'right');
    for(let i=0;i<count;i++) {
      const choice=data.choices[i];
      const px=x(choice.time_ns),py=y(choice.response.diff_mV);
      const color=choice.observation.decision===1?colors.green:colors.orange;
      if(i===selected) {
        ctx.fillStyle='#e1ebdf';ctx.fillRect(px-9,top-3,18,bottom-top+7);
      }
      ctx.lineWidth=i===selected?2.3:1.4;
      line(ctx,px,y(0),px,py,color);
      ctx.beginPath();ctx.arc(px,py,i===selected?5:3.5,0,2*Math.PI);
      ctx.fillStyle=color;ctx.fill();
      if(i===selected) {ctx.strokeStyle='white';ctx.lineWidth=1.5;ctx.stroke();}
      label(ctx,String(i+1),px,y(0)-8,i===selected?colors.ink:colors.muted,'center');
    }
    ctx.lineWidth=1;
    const stopX=x(data.duration_ns);
    line(ctx,stopX,top,stopX,bottom,selected===count?colors.green:'#ccd6cc');
    label(ctx,'Stop',stopX,12,selected===count?colors.green:colors.muted,'right');
    for(let t=0;t<=data.duration_ns;t+=width<400?80:40) label(ctx,String(t),x(t),height-12,colors.muted,'center');
    label(ctx,'Pause time · ns',right,height-1,colors.muted,'right');
    $('stems').setAttribute('aria-label', `AI-chosen external differential inputs in millivolts: ${data.choices.map(c=>`${c.number}: ${signed(c.response.diff_mV)}`).join('; ')}. Fixed +43 millivolt device offset; dashed cancellation line at −43 millivolts. Use the decision buttons to select an experiment.`);
  }
  function tooltip(output,canvas,event,text) {
    const rect=canvas.getBoundingClientRect();
    output.textContent=text;output.hidden=false;
    output.style.left=Math.max(0,Math.min(event.clientX-rect.left+12,rect.width-output.offsetWidth-4))+'px';
    output.style.top=Math.max(0,Math.min(event.clientY-rect.top-18,rect.height-output.offsetHeight))+'px';
  }
  const waveCanvas=$('waveforms'),stemCanvas=$('stems');
  waveCanvas.addEventListener('pointermove',event=>{
    if(!waveGeometry) return;
    const px=event.clientX-waveCanvas.getBoundingClientRect().left;
    const {left,right,start,end}=waveGeometry;
    if(px<left||px>right) {$('wave-cursor').hidden=true;return;}
    const time=start+(px-left)/(right-left)*(end-start);
    let index=Math.min(points.length-1,lowerBound(time));
    if(index>0&&time-points[index-1][0]<points[index][0]-time) index--;
    const p=points[index];
    tooltip($('wave-cursor'),waveCanvas,event,`${number(p[0],4)} ns\nCLK  ${number(p[1],4)} V\nOUTP ${number(p[2],4)} V\nOUTN ${number(p[3],4)} V\nΔV   ${number(p[4],6)} mV`);
  });
  function nearestStem(event) {
    if(!stemGeometry) return 0;
    const px=event.clientX-stemCanvas.getBoundingClientRect().left;
    let index=0,distance=Infinity;
    for(let i=0;i<=count;i++) {
      const d=Math.abs(px-stemGeometry.x(i===count?data.duration_ns:data.choices[i].time_ns));
      if(d<distance) {distance=d;index=i;}
    }
    return index;
  }
  stemCanvas.style.cursor='pointer';
  stemCanvas.addEventListener('click',event=>select(nearestStem(event)));
  stemCanvas.addEventListener('pointermove',event=>{
    const i=nearestStem(event);
    const c=data.choices[i];
    tooltip($('stem-cursor'),stemCanvas,event,i===count?`Call ${count+1} · ${number(data.duration_ns)} ns\nStop · no new stimulus`:`Experiment ${i+1} · ${number(c.time_ns)} ns\nInput ${signed(c.response.diff_mV)} mV\nMeasured decision ${c.observation.decision}`);
  });
  [[waveCanvas,$('wave-cursor')],[stemCanvas,$('stem-cursor')]].forEach(([canvas,output])=>canvas.addEventListener('pointerleave',()=>{output.hidden=true;}));
  new ResizeObserver(scheduleDraw).observe($('waveforms').parentElement);
  window.addEventListener('resize',scheduleDraw);
  select(0);
})();

let refreshing=false;
let currentAudioId='';
let currentAudio=null;

function autoAnimation(style){
  if(['angry','shouting','terrified'].includes(style))return 'shake';
  if(['excited','cheerful'].includes(style))return 'bounce';
  if(['whispering','calm','sad'].includes(style))return 'pulse';
  return 'talk';
}
function applyCharacter(n,p,c){
  const stage=document.getElementById(`character-stage-${n}`),img=document.getElementById(`character-${n}`);
  if(!c||!c.configured){stage.classList.remove('visible');img.removeAttribute('src');return}
  if(img.dataset.src!==c.url){img.src=c.url;img.dataset.src=c.url}
  stage.classList.add('visible');stage.style.setProperty('--char-size',`${c.size}px`);stage.style.setProperty('--char-x',`${c.x}px`);stage.style.setProperty('--char-y',`${c.y}px`);stage.style.setProperty('--mirror',c.mirror?-1:1);
  const motion=4+(Number(c.intensity)||0)*3,tilt=1+(Number(c.intensity)||0)*0.45;
  img.style.setProperty('--motion',`${motion}px`);img.style.setProperty('--tilt',`${tilt}deg`);img.className='character-img';
  if(p.speaking){let anim=c.speaking==='auto'?autoAnimation(p.effective_style):c.speaking;if(anim!=='none')img.classList.add(`speaking-${anim}`)}
  else if(c.idle!=='none')img.classList.add(`idle-${c.idle}`);
}
async function post(url){try{await fetch(url,{method:'POST'})}catch(_){}}
async function hello(){await post('/api/audio/hello')}
function maybePlayAudio(audioState){
  const item=audioState&&audioState.current;
  if(!item||item.id===currentAudioId)return;
  currentAudioId=item.id;
  if(currentAudio){try{currentAudio.pause()}catch(_){}}
  const audio=new Audio(item.url);currentAudio=audio;audio.preload='auto';
  audio.onplaying=()=>post(`/api/audio/${item.id}/started`);
  audio.onended=()=>post(`/api/audio/${item.id}/finished`);
  audio.onerror=()=>post(`/api/audio/${item.id}/finished`);
  audio.play().catch(()=>post(`/api/audio/${item.id}/finished`));
}
async function refreshOverlay(){
  if(refreshing)return;refreshing=true;
  try{
    const r=await fetch('/api/state',{cache:'no-store'}),d=await r.json();
    const count=Math.max(1,Math.min(Number(d.active_players||1),3));
    document.querySelector('.overlay-grid').style.gridTemplateColumns=`repeat(${count},1fr)`;
    for(const n of ['1','2','3']){
      const section=document.getElementById(`overlay-player-${n}`),active=Number(n)<=count;
      section.style.display=active?'':'none';if(!active)continue;
      const p=d.players[n];document.getElementById('user-'+n).textContent=p.user||('Jogador '+n);document.getElementById('message-'+n).textContent=p.message||'Aguardando mensagem...';applyCharacter(n,p,d.characters[n]);
    }
    maybePlayAudio(d.audio);
  }catch(_){}finally{refreshing=false}
}
function connectEvents(){try{const events=new EventSource('/api/events');events.onmessage=()=>refreshOverlay();events.onerror=()=>{};}catch(_){}}
hello();setInterval(hello,5000);refreshOverlay();connectEvents();setInterval(refreshOverlay,5000);

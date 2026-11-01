/* ════════════════════════════════════════════════════════════
   TG Vibes — script.js  v2  FULL FIXED
   Fixes:
   ✅ Song thumbnail not loading (first song)
   ✅ Queue empty → room link expire → show "play new song" screen
   ✅ Call overlay: nav still works (floating sheet, not full screen)
   ✅ Autoplay: /autoplay command + auto fetch next song
   ✅ Full powerful profile: badges, chart, mood, friends, top artists
   ✅ Notifications polling
   ✅ Theme color customization
   ✅ Bio editing
   ✅ Friends add/remove
   ✅ No duplicate volume/speed controls
   ════════════════════════════════════════════════════════════ */

// ── Telegram ──────────────────────────────────────────────
const tg = window.Telegram?.WebApp;
if (tg) {
    tg.expand();
    tg.setHeaderColor     && tg.setHeaderColor('#f2f2f7');
    tg.setBackgroundColor && tg.setBackgroundColor('#f2f2f7');
}

// ── Dark mode ─────────────────────────────────────────────
const dmToggle = document.getElementById('darkmode-toggle');
if (dmToggle) dmToggle.addEventListener('change', () => {
    document.body.classList.toggle('dark', dmToggle.checked);
    const col = dmToggle.checked ? '#000' : '#f2f2f7';
    tg?.setHeaderColor     && tg.setHeaderColor(col);
    tg?.setBackgroundColor && tg.setBackgroundColor(col);
});

// ── User ──────────────────────────────────────────────────
const tgUser    = tg?.initDataUnsafe?.user;
const userId    = tgUser?.id   || 0;
const firstName = tgUser?.first_name || '';
const lastName  = tgUser?.last_name  || '';
const username  = (firstName + (lastName ? ' ' + lastName : '')).trim() || ('Guest_' + ~~(Math.random()*9000+1000));
const userHandle= tgUser?.username  || '';
const userPhoto = tgUser?.photo_url || null;
const initials  = username.trim().split(' ').map(w=>w[0]).join('').toUpperCase().slice(0,2) || '?';

// ── URL params ────────────────────────────────────────────
const urlP      = new URLSearchParams(window.location.search);
let playLink='', playTitle='Unknown', playDuration='0:00', roomChatId=0;

function decodeChatId(s){
    s=(s||'').trim();
    if(s.startsWith('N')) return -parseInt(s.slice(1),10)||0;
    const n=parseInt(s,10); return isNaN(n)?0:n;
}
function parseStartParam(raw){
    if(!raw) return;
    try{
        let b64=raw.replace(/-/g,'+').replace(/_/g,'/');
        const rem=b64.length%4; if(rem) b64+='='.repeat(4-rem);
        let dec; try{dec=atob(b64);}catch{dec=decodeURIComponent(raw);}
        if(!dec.includes('|')) dec=decodeURIComponent(raw);
        const parts=dec.split('|');
        const chatIdEnc=parts[parts.length-1]||'0';
        const durPart  =parts[parts.length-2]||'0:00';
        const linkPart =parts[0]||'';
        const titleRaw =parts.slice(1,parts.length-2).join('|');
        playLink    =linkPart.startsWith('ytid:')
            ?'https://www.youtube.com/watch?v='+linkPart.replace('ytid:','').trim()
            :linkPart.trim();
        playTitle   =titleRaw.replace(/¦/g,'|').trim()||'Unknown';
        playDuration=durPart.trim()||'0:00';
        roomChatId  =decodeChatId(chatIdEnc);
    }catch(e){console.error('[parse]',e);}
}
const tgParam=tg?.initDataUnsafe?.start_param;
if(tgParam) parseStartParam(tgParam);
if(!playLink&&!roomChatId){const u=urlP.get('startapp');if(u) parseStartParam(u);}
if(!playLink)    playLink    =urlP.get('play')||'';
if(!roomChatId)  roomChatId  =parseInt(urlP.get('chat_id')||'0')||0;

// ── DOM refs ──────────────────────────────────────────────
const audio         =document.getElementById('audio-player');
const playPauseBtn  =document.getElementById('play-pause-btn');
const progressFill  =document.getElementById('progress-bar-fill');
const progressThumb =document.getElementById('progress-thumb');
const progressBar   =document.getElementById('progress-bar');
const currentTimeEl =document.getElementById('current-time');
const totalTimeEl   =document.getElementById('total-time');
const songTitleEl   =document.getElementById('song-title');
const songSubEl     =document.getElementById('song-sub');
const albumArt      =document.getElementById('album-art');
const songThumb     =document.getElementById('song-thumb');
const artIconWrap   =document.getElementById('art-icon-wrap');
const artGlow       =document.getElementById('art-glow');
const queueList     =document.getElementById('queue-list');
const queueCount    =document.getElementById('queue-count');
const listenersList =document.getElementById('listeners-list');
const listenersCount=document.getElementById('listeners-count');
const chatMsgsEl    =document.getElementById('chat-messages');
const chatInput     =document.getElementById('chat-input');
const volumeSlider  =document.getElementById('volume-slider');
const volFill       =document.getElementById('vol-fill');

// ── State ─────────────────────────────────────────────────
let socket=null, wsReconnectDelay=2500;
let isDragging=false, pendingSeek=-1, initialSeekDone=false;
let currentSongUrl='', currentSongTitle='', currentSongLink='', currentDurationSec=0;
let isPlaying=false, hasJoined=false, currentTab='player';
let progressTimer=null, listenStart=null;
let favoriteSongs=[], repeatMode=false, shuffleMode=false;
let currentThumbUrl='', _playLinkRequested=false;
let currentBassLevel='off', currentSpeed=1.0;
let userThemeColor='#007aff';
let autoplayEnabled=false, autoplayQuery='';
let sessionSeconds=0, sessionTimer=null;
let profileData={};
let callOverlayVisible=false;

// ══════════════════════════════════════════════════════════
//  THEME COLOR
// ══════════════════════════════════════════════════════════
function applyThemeColor(color){
    userThemeColor=color;
    document.documentElement.style.setProperty('--accent',color);
    // gradient on banner + ring
    const banner=document.getElementById('profile-banner');
    const ring  =document.getElementById('profile-av-ring');
    const av    =document.getElementById('profile-avatar');
    if(banner) banner.style.background=`linear-gradient(135deg,${color},${lighten(color,30)})`;
    if(ring)   ring.style.background=`linear-gradient(135deg,${color},${lighten(color,30)})`;
    tg?.setHeaderColor && tg.setHeaderColor(color);
}
function lighten(hex,amt){
    let c=hex.replace('#','');
    if(c.length===3) c=c.split('').map(x=>x+x).join('');
    const n=parseInt(c,16);
    const r=Math.min(255,((n>>16)&0xff)+amt);
    const g=Math.min(255,((n>>8)&0xff)+amt);
    const b=Math.min(255,(n&0xff)+amt);
    return '#'+[r,g,b].map(x=>x.toString(16).padStart(2,'0')).join('');
}
document.getElementById('edit-theme-btn')?.addEventListener('click',()=>{
    const tp=document.getElementById('theme-picker');
    if(tp) tp.style.display=tp.style.display==='none'?'block':'none';
});
document.querySelectorAll('.tp-color').forEach(btn=>{
    btn.addEventListener('click',()=>{
        document.querySelectorAll('.tp-color').forEach(b=>b.classList.remove('selected'));
        btn.classList.add('selected');
        applyThemeColor(btn.dataset.color);
        fetch(`/profile/update?user_id=${userId}&theme_color=${encodeURIComponent(btn.dataset.color)}`,{method:'POST'}).catch(()=>{});
        gsap.from(btn,{scale:0.7,duration:.2,ease:'back.out(3)'});
    });
});

// ══════════════════════════════════════════════════════════
//  GSAP ANIMATIONS
// ══════════════════════════════════════════════════════════
function animateJoinScreen(){
    gsap.timeline()
        .from('#join-logo', {scale:.5,opacity:0,duration:.6,ease:'back.out(2)'})
        .from('.join-title',{y:20,opacity:0,duration:.4,ease:'power2.out'},'-=.2')
        .from('.join-sub',  {y:15,opacity:0,duration:.4,ease:'power2.out'},'-=.3')
        .from('.join-btn',  {y:20,opacity:0,duration:.5,ease:'back.out(1.5)'},'-=.2');
}
function animateMainAppIn(){
    gsap.from('#art-wrapper',  {scale:.85,opacity:0,duration:.6,ease:'back.out(1.5)',delay:.1});
    gsap.from('.song-info-row',{y:20,opacity:0,duration:.5,ease:'power2.out',delay:.3});
    gsap.from('.progress-wrap',{y:16,opacity:0,duration:.4,ease:'power2.out',delay:.4});
    gsap.from('.controls-row', {y:16,opacity:0,duration:.4,ease:'power2.out',delay:.5});
    gsap.from('.ctrl-slider-row,.pills-section,.seek-row',
        {y:12,opacity:0,duration:.4,stagger:.07,ease:'power2.out',delay:.6});
    gsap.from('.bottom-nav',   {y:80,duration:.5,ease:'back.out(1.5)',delay:.2});
}
function animateTabSwitch(tabName){
    const page=document.getElementById('page-'+tabName);
    if(!page) return;
    gsap.fromTo(page,{opacity:0,y:12},{opacity:1,y:0,duration:.3,ease:'power2.out'});
}
function animateArtChange(){
    gsap.to('#album-art',{scale:.93,duration:.15,ease:'power1.in',
        onComplete:()=>gsap.to('#album-art',{scale:1,duration:.4,ease:'back.out(2)'})});
}

// ══════════════════════════════════════════════════════════
//  JOIN / MAIN APP
// ══════════════════════════════════════════════════════════
function showJoinScreen(){
    document.getElementById('join-screen').style.display='flex';
    document.getElementById('main-app').style.display='none';
    const infoEl=document.getElementById('join-song-info');
    if(playTitle&&playTitle!=='Unknown'){
        infoEl.style.display='flex';
        document.getElementById('join-song-name').textContent=playTitle;
        document.getElementById('join-song-dur').textContent=playDuration;
    } else if(roomChatId){
        fetch(`/status?chat_id=${roomChatId}`).then(r=>r.json()).then(d=>{
            if(d.current_song?.title){
                infoEl.style.display='flex';
                document.getElementById('join-song-name').textContent=d.current_song.title;
                const sec=d.current_song.duration_sec||0;
                document.getElementById('join-song-dur').textContent=sec?formatSec(sec):'';
                const th=document.getElementById('join-thumb-wrap');
                if(th&&d.current_song.thumbnail)
                    th.innerHTML=`<img src="${d.current_song.thumbnail}" style="width:100%;height:100%;object-fit:cover;border-radius:10px;" onerror="this.remove()">`;
            }
        }).catch(()=>{});
    }
    animateJoinScreen();
}
function showMainApp(){
    document.getElementById('join-screen').style.display='none';
    document.getElementById('main-app').style.display='block';
    animateMainAppIn();
}
function joinRoom(){
    const btn=document.getElementById('join-btn');
    gsap.to(btn,{scale:.95,duration:.1,onComplete:()=>gsap.to(btn,{scale:1,duration:.2})});
    btn.disabled=true; btn.innerHTML='<i class="fas fa-spinner fa-spin"></i> Joining...';
    hasJoined=true;
    showMainApp();
    connectWS();
    loadProfile();
    loadFavorites();
    refreshProfileUI();
    startNotifPoller();
}

// ══════════════════════════════════════════════════════════
//  TAB SWITCHING — call overlay stays, nav always works
// ══════════════════════════════════════════════════════════
function switchTab(tab){
    currentTab=tab;
    document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(b=>b.classList.remove('active'));
    const page=document.getElementById('page-'+tab);
    const nav =document.getElementById('nav-'+tab);
    if(page) page.classList.add('active');
    if(nav)  nav.classList.add('active');
    // Keep call-active style if in call
    if(callState.inCall) document.getElementById('nav-call')?.classList.add('call-active');
    animateTabSwitch(tab);
    if(tab==='chat')    document.getElementById('chat-badge').style.display='none';
    if(tab==='profile') loadProfile();
    if(tab==='playlist'){renderFavoritesList();}
    const ni=document.getElementById('ni-'+tab);
    if(ni) gsap.fromTo(ni,{y:-4},{y:0,duration:.35,ease:'back.out(3)'});
}

// ══════════════════════════════════════════════════════════
//  CALL OVERLAY — floating sheet, nav always accessible
// ══════════════════════════════════════════════════════════
function toggleCallOverlay(){
    if(callState.inCall){
        // Already in call — toggle visibility
        callOverlayVisible=!callOverlayVisible;
        const ov=document.getElementById('call-overlay');
        if(callOverlayVisible){
            ov.style.display='block';
            gsap.fromTo(ov,{y:100,opacity:0},{y:0,opacity:1,duration:.35,ease:'back.out(1.5)'});
        } else {
            gsap.to(ov,{y:60,opacity:0,duration:.25,ease:'power2.in',onComplete:()=>ov.style.display='none'});
        }
    } else {
        // Not in call — join
        joinCall();
    }
}
function collapseCallOverlay(){
    callOverlayVisible=false;
    const ov=document.getElementById('call-overlay');
    gsap.to(ov,{y:60,opacity:0,duration:.25,ease:'power2.in',onComplete:()=>ov.style.display='none'});
    // Nav still works — user can switch tabs freely
}

// ══════════════════════════════════════════════════════════
//  ROOM EXPIRED — show "play new song" screen
// ══════════════════════════════════════════════════════════
async function handleRoomExpired(){
    if(!roomChatId) return;
    try{
        const r=await fetch(`/room_expired?chat_id=${roomChatId}`);
        const d=await r.json();
        if(d.status==='autoplay_available'&&d.results?.length>0){
            // Autoplay: queue first result automatically
            const s=d.results[0];
            showToast('🔄 Autoplay: loading '+s.title.slice(0,25)+'...');
            await fetch(`/play_song?link=${encodeURIComponent(s.link)}&title=${encodeURIComponent(s.title)}&duration=${encodeURIComponent(s.duration||'0:00')}&chat_id=${roomChatId}&user_id=${userId}`,{method:'POST'});
        } else {
            // Show expired message inline
            songTitleEl.textContent='Session Ended';
            songSubEl.textContent='Open your group and use /play to start again';
            addSystemMsg('⏸ Room is empty. Go to your Telegram group and use /play to start a new session!');
            showExpiredCard();
        }
    }catch(e){console.error('[roomExpired]',e);}
}

function showExpiredCard(){
    // Remove old if exists
    document.getElementById('expired-card')?.remove();
    const card=document.createElement('div');
    card.id='expired-card';
    card.style.cssText='position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);'+
        'background:var(--surface);border-radius:20px;padding:28px;text-align:center;'+
        'box-shadow:var(--shadow-md);z-index:50;width:min(300px,calc(100vw - 40px));';
    card.innerHTML=`
        <div style="font-size:40px;margin-bottom:12px">⏸</div>
        <div style="font-size:18px;font-weight:700;color:var(--text);margin-bottom:6px">Session Ended</div>
        <div style="font-size:13px;color:var(--text2);margin-bottom:16px">Queue is empty. Use /play in your Telegram group to start a new song!</div>
        <button onclick="this.parentElement.remove()" style="background:var(--accent);color:#fff;border:none;border-radius:12px;padding:10px 24px;font-size:14px;font-weight:600;cursor:pointer;">Got it</button>`;
    document.body.appendChild(card);
    gsap.from(card,{scale:.85,opacity:0,duration:.35,ease:'back.out(2)'});
}

// ══════════════════════════════════════════════════════════
//  WEBSOCKET
// ══════════════════════════════════════════════════════════
function connectWS(){
    const proto=location.protocol==='https:'?'wss:':'ws:';
    socket=new WebSocket(`${proto}//${location.host}/ws/${roomChatId}/${encodeURIComponent(username)}?user_id=${userId}`);
    socket.onopen=()=>{wsReconnectDelay=2500;};
    socket.onclose=()=>{
        if(hasJoined) setTimeout(connectWS,wsReconnectDelay);
        wsReconnectDelay=Math.min(wsReconnectDelay*1.5,30000);
    };
    socket.onerror=e=>console.error('[WS]',e);
    socket.onmessage=e=>{
        try{
            const data=JSON.parse(e.data);
            if(['call_join','call_leave','call_mute','webrtc_offer','webrtc_answer','webrtc_ice'].includes(data.type)){
                _handleCallSignal(data); return;
            }
            if(data.type==='state_update'){
                if(!_playLinkRequested&&hasJoined&&playLink){
                    _playLinkRequested=true;
                    if(!data.current_song) checkPlayLink();
                }
                renderState(data);
            } else if(data.type==='chat'){
                if(data.username===username) return;
                const sub=data.sub_type||'text';
                if(sub==='voice') addChatMsg(data.message,data.username,false,'voice');
                else if(sub==='media') addChatMsg(data.message,data.username,false,'media',0,{mime:data.mime||'',filename:data.filename||'file'});
                else addChatMsg(data.message,data.username,false,'text');
                if(currentTab==='chat'&&socket.readyState===WebSocket.OPEN)
                    socket.send(JSON.stringify({type:'seen',username}));
            } else if(data.type==='typing'){
                if(data.username===username) return;
                if(data.is_typing) _typingUsers.add(data.username);
                else               _typingUsers.delete(data.username);
                _showTypingBar();
                setTimeout(()=>{_typingUsers.delete(data.username);_showTypingBar();},3000);
            } else if(data.type==='seen'){
                if(data.username!==username) _updateSeen(data.username);
            } else if(data.type==='system'){
                addSystemMsg(data.message);
            }
        }catch(err){console.error('[WS parse]',err);}
    };
}

// ══════════════════════════════════════════════════════════
//  RENDER STATE  (fixes thumbnail + expired room)
// ══════════════════════════════════════════════════════════
function renderState(data){
    const online=data.listeners?.length||0;
    document.getElementById('chat-online-count').textContent=online+' online';
    if(listenersCount) listenersCount.textContent=online;

    // Autoplay indicator
    const apEnabled=data.autoplay||false;
    const apQuery  =data.autoplay_query||'';
    document.getElementById('autoplay-indicator').style.display=apEnabled?'flex':'none';
    document.getElementById('autoplay-label').textContent=apEnabled?('Autoplay: '+apQuery):'';

    if(data.current_song){
        const song=data.current_song;
        const rawUrl=song.url||'';
        const absUrl=rawUrl.startsWith('http')?rawUrl:(rawUrl?location.origin+rawUrl:'');
        const dur=song.duration_sec||0;
        const serverSeek=parseFloat(data.seek_time)||0;

        if(dur>0){
            currentDurationSec=dur;
            totalTimeEl.textContent=formatTime(dur);
            progressBar.max=dur;
        }

        if(absUrl&&absUrl!==currentSongUrl){
            currentSongUrl=absUrl;
            currentSongTitle=song.title||'Unknown';
            currentSongLink=song.link||'';
            initialSeekDone=false;
            pendingSeek=serverSeek;

            songTitleEl.textContent=currentSongTitle;
            songSubEl.textContent='TG Vibes • Live Session';
            document.getElementById('np-title').textContent=currentSongTitle;
            const nmc=document.getElementById('nmc-title');
            if(nmc) nmc.textContent=currentSongTitle;

            document.getElementById('fav-btn')?.classList.remove('active');

            // ✅ FIX: Always set thumbnail if available (fixes first song issue)
            const thumb=song.thumbnail||'';
            if(thumb){
                currentThumbUrl=thumb;
                // Use img element properly
                const img=document.getElementById('song-thumb');
                img.onload=()=>{
                    img.style.display='block';
                    img.classList.add('show');
                    if(artIconWrap) artIconWrap.style.display='none';
                    if(artGlow) artGlow.style.background=`radial-gradient(ellipse,rgba(0,122,255,.22) 0%,transparent 70%)`;
                };
                img.onerror=()=>{
                    img.style.display='none';
                    img.classList.remove('show');
                    if(artIconWrap) artIconWrap.style.display='flex';
                };
                img.src=''; // Reset first to force onload
                img.src=thumb;
                // NMC thumb
                const nmcThumb=document.getElementById('nmc-thumb');
                if(nmcThumb) nmcThumb.innerHTML=`<img src="${thumb}" onerror="this.remove()" style="width:100%;height:100%;object-fit:cover;border-radius:10px;">`;
                // Join thumb
                const jt=document.getElementById('join-thumb-wrap');
                if(jt) jt.innerHTML=`<img src="${thumb}" style="width:100%;height:100%;object-fit:cover;border-radius:10px;" onerror="this.remove()">`;
            } else {
                currentThumbUrl='';
                songThumb.src='';
                songThumb.style.display='none';
                songThumb.classList.remove('show');
                if(artIconWrap) artIconWrap.style.display='flex';
                if(artGlow) artGlow.style.background='';
            }

            document.getElementById('now-mini').style.display='flex';
            animateArtChange();

            audio.src=absUrl;
            audio.preload='auto';
            audio.load();
            addSystemMsg('▶ Now playing: '+currentSongTitle);

        } else if(absUrl&&!initialSeekDone){
            const diff=Math.abs(audio.currentTime-serverSeek);
            if(diff>2&&audio.readyState>=1){audio.currentTime=serverSeek;initialSeekDone=true;}
            else if(diff>2){pendingSeek=serverSeek;}
            else{initialSeekDone=true;}
        } else if(absUrl&&!isDragging){
            const diff=Math.abs(audio.currentTime-serverSeek);
            if(diff>5&&audio.readyState>=1) audio.currentTime=serverSeek;
        }

        isPlaying=data.is_playing;
        if(data.is_playing){
            if(absUrl&&audio.paused&&audio.readyState>=2){
                audio.play().catch(showAutoplayOverlay);
            } else if(absUrl&&audio.paused){
                audio.oncanplay=()=>{audio.play().catch(showAutoplayOverlay);audio.oncanplay=null;};
            }
            playPauseBtn.innerHTML='<i class="fas fa-pause"></i>';
            albumArt.classList.add('spin');
            if(!listenStart){listenStart=Date.now();startSessionTimer();}
            startProgressTimer();
        } else {
            audio.pause();
            playPauseBtn.innerHTML='<i class="fas fa-play"></i>';
            albumArt.classList.remove('spin');
            stopSessionTimer();
            listenStart=null;
            stopProgressTimer();
            updateProgressUI(serverSeek,currentDurationSec);
        }

        if(data.bass_config) _applyBassConfig(data.bass_config);

    } else {
        // ✅ FIX: No song — check if was playing before → room expired
        if(currentSongUrl){
            const wasPlaying=isPlaying;
            currentSongUrl='';currentSongTitle='';currentSongLink='';currentThumbUrl='';
            currentDurationSec=0;isPlaying=false;initialSeekDone=false;
            audio.pause();audio.src='';
            stopProgressTimer();stopSessionTimer();
            songTitleEl.textContent='No Song Playing';
            songSubEl.textContent='TG Vibes • Live Session';
            document.getElementById('np-title').textContent='Nothing Playing';
            const nmc=document.getElementById('nmc-title');
            if(nmc) nmc.textContent='–';
            playPauseBtn.innerHTML='<i class="fas fa-play"></i>';
            albumArt.classList.remove('spin');
            songThumb.src='';songThumb.style.display='none';songThumb.classList.remove('show');
            if(artIconWrap) artIconWrap.style.display='flex';
            if(artGlow) artGlow.style.background='';
            updateProgressUI(0,0);
            listenStart=null;
            document.getElementById('now-mini').style.display='none';
            _playLinkRequested=false;
            if(wasPlaying) setTimeout(()=>handleRoomExpired(),1500);
        }
    }

    // Queue
    const queue=data.queue||[];
    const qBadge=document.getElementById('queue-badge');
    if(queue.length>0){
        if(qBadge) qBadge.style.display='block';
        if(queueCount) queueCount.textContent=queue.length+' songs';
        if(queueList) queueList.innerHTML=queue.map((item,i)=>`
            <div class="q-item">
                <div class="q-num">${i+2}</div>
                <div class="q-info">
                    <div class="q-title">${escHtml(item.title||'Unknown')}</div>
                    <div class="q-dur">${formatSec(item.duration_sec||0)}</div>
                </div>
            </div>`).join('');
    } else {
        if(qBadge) qBadge.style.display='none';
        if(queueCount) queueCount.textContent='0 songs';
        if(queueList) queueList.innerHTML='<p style="padding:16px;color:var(--text3);font-size:13px;text-align:center;">Queue is empty. Use /play to add songs.</p>';
    }

    // Listeners
    if(listenersList){
        listenersList.innerHTML='';
        (data.listeners||[]).forEach(l=>{
            const chip=document.createElement('div');
            chip.className='listener-chip';
            chip.textContent=l.username||'Unknown';
            listenersList.appendChild(chip);
        });
    }
}

// ══════════════════════════════════════════════════════════
//  AUDIO EVENTS
// ══════════════════════════════════════════════════════════
audio.onloadedmetadata=()=>{
    currentDurationSec=audio.duration||currentDurationSec;
    totalTimeEl.textContent=formatTime(currentDurationSec);
    progressBar.max=currentDurationSec;
    if(pendingSeek>=0){audio.currentTime=pendingSeek;pendingSeek=-1;initialSeekDone=true;}
};
audio.ontimeupdate=()=>{
    if(!isDragging&&currentDurationSec>0) updateProgressUI(audio.currentTime,currentDurationSec);
};
audio.onended=()=>{
    stopProgressTimer();
    if(repeatMode){audio.currentTime=0;audio.play().catch(()=>{});return;}
    logListenSession();
    // Autoplay
    if(autoplayEnabled){
        fetchAutoplayNext();
    } else if(socket&&socket.readyState===WebSocket.OPEN){
        socket.send(JSON.stringify({type:'skip'}));
    }
};
audio.onerror=async()=>{
    if(!currentSongLink) return;
    try{
        const r=await fetch(`/refresh_url?link=${encodeURIComponent(currentSongLink)}&chat_id=${roomChatId}`);
        if(r.ok){
            const d=await r.json();
            if(d.url){
                const absUrl=d.url.startsWith('http')?d.url:location.origin+d.url;
                const wasAt=audio.currentTime,wasPlay=!audio.paused;
                audio.src=absUrl;currentSongUrl=absUrl;audio.load();
                audio.oncanplay=()=>{audio.currentTime=wasAt;if(wasPlay) audio.play().catch(showAutoplayOverlay);audio.oncanplay=null;};
            }
        }
    }catch{}
};

progressBar.oninput =()=>{isDragging=true;updateProgressUI(+progressBar.value,currentDurationSec);};
progressBar.onchange=()=>{
    isDragging=false;audio.currentTime=+progressBar.value;
    if(socket?.readyState===WebSocket.OPEN)
        socket.send(JSON.stringify({type:'seek',seek_time:+progressBar.value}));
};
document.querySelector('.progress-track')?.addEventListener('click',e=>{
    if(!currentDurationSec) return;
    const rect=document.querySelector('.progress-track').getBoundingClientRect();
    const t=(e.clientX-rect.left)/rect.width*currentDurationSec;
    audio.currentTime=t;updateProgressUI(t,currentDurationSec);
    if(socket?.readyState===WebSocket.OPEN) socket.send(JSON.stringify({type:'seek',seek_time:t}));
});

// Progress UI
function updateProgressUI(cur,dur){
    if(!dur||dur<=0){progressFill.style.width='0%';progressThumb.style.left='0%';progressBar.value=0;currentTimeEl.textContent='0:00';return;}
    const pct=Math.min((cur/dur)*100,100);
    progressFill.style.width=pct+'%';progressThumb.style.left=pct+'%';
    progressBar.value=cur;progressBar.max=dur;
    currentTimeEl.textContent=formatTime(cur);
    totalTimeEl.textContent=formatTime(dur);
}
function startProgressTimer(){if(progressTimer) return;progressTimer=setInterval(()=>{if(!isDragging&&isPlaying&&currentDurationSec>0) updateProgressUI(audio.currentTime||0,currentDurationSec);},500);}
function stopProgressTimer(){if(progressTimer){clearInterval(progressTimer);progressTimer=null;}}

// Session timer for stats
function startSessionTimer(){
    if(sessionTimer) return;
    sessionTimer=setInterval(()=>{sessionSeconds++;},1000);
}
function stopSessionTimer(){if(sessionTimer){clearInterval(sessionTimer);sessionTimer=null;}}

// ══════════════════════════════════════════════════════════
//  AUTOPLAY FETCH
// ══════════════════════════════════════════════════════════
async function fetchAutoplayNext(){
    try{
        const r=await fetch(`/autoplay/next?chat_id=${roomChatId}&current_title=${encodeURIComponent(currentSongTitle)}`);
        const d=await r.json();
        if(d.status==='ok'&&d.song){
            showToast('🔄 Autoplay: '+d.song.title.slice(0,28)+'...');
            await fetch(`/play_song?link=${encodeURIComponent(d.song.link)}&title=${encodeURIComponent(d.song.title)}&duration=${encodeURIComponent(d.song.duration||'0:00')}&chat_id=${roomChatId}&user_id=${userId}`,{method:'POST'});
        } else {
            // No autoplay result, skip via bot
            socket?.readyState===WebSocket.OPEN&&socket.send(JSON.stringify({type:'skip'}));
        }
    }catch{
        socket?.readyState===WebSocket.OPEN&&socket.send(JSON.stringify({type:'skip'}));
    }
}

// ══════════════════════════════════════════════════════════
//  VOLUME (single, no duplicate)
// ══════════════════════════════════════════════════════════
volumeSlider.oninput=()=>{
    const vol=parseFloat(volumeSlider.value);
    audio.volume=vol;
    if(volFill) volFill.style.width=(vol*100)+'%';
    const icon=document.getElementById('vol-icon');
    if(!icon) return;
    icon.className=vol===0?'fas fa-volume-xmark ctrl-icon':vol<.5?'fas fa-volume-low ctrl-icon':'fas fa-volume-high ctrl-icon';
};
if(volFill) volFill.style.width='100%';
document.getElementById('mute-btn')?.addEventListener('click',()=>{
    audio.muted=!audio.muted;
    const v=audio.muted?0:audio.volume;
    if(volFill) volFill.style.width=(v*100)+'%';
    const icon=document.getElementById('vol-icon');
    if(icon) icon.className=audio.muted?'fas fa-volume-xmark ctrl-icon':'fas fa-volume-high ctrl-icon';
});

// ══════════════════════════════════════════════════════════
//  SPEED (single)
// ══════════════════════════════════════════════════════════
document.querySelectorAll('#speed-pills .ios-pill').forEach(btn=>{
    btn.onclick=()=>{
        document.querySelectorAll('#speed-pills .ios-pill').forEach(b=>b.classList.remove('active'));
        btn.classList.add('active');
        currentSpeed=parseFloat(btn.dataset.speed);
        audio.playbackRate=currentSpeed;
        gsap.from(btn,{scale:.85,duration:.2,ease:'back.out(2)'});
    };
});

// ══════════════════════════════════════════════════════════
//  BASS (single)
// ══════════════════════════════════════════════════════════
const BASS_CFG={off:{gain:0,freq:60},low:{gain:4,freq:80},medium:{gain:9,freq:100},high:{gain:14,freq:120},extreme:{gain:20,freq:150}};
document.querySelectorAll('#bass-pills .ios-pill').forEach(btn=>{
    btn.onclick=()=>{
        document.querySelectorAll('#bass-pills .ios-pill').forEach(b=>b.classList.remove('active'));
        btn.classList.add('active');
        currentBassLevel=btn.dataset.bass;
        const cfg=BASS_CFG[currentBassLevel]||BASS_CFG.off;
        _applyBassConfig({level:currentBassLevel,...cfg});
        gsap.from(btn,{scale:.85,duration:.2,ease:'back.out(2)'});
        socket?.readyState===WebSocket.OPEN&&socket.send(JSON.stringify({type:'bass',level:currentBassLevel,...cfg}));
    };
});

// ══════════════════════════════════════════════════════════
//  CONTROLS
// ══════════════════════════════════════════════════════════
playPauseBtn.onclick=()=>{
    if(!socket||socket.readyState!==WebSocket.OPEN) return;
    gsap.to(playPauseBtn,{scale:.88,duration:.1,ease:'power1.in',onComplete:()=>gsap.to(playPauseBtn,{scale:1,duration:.3,ease:'back.out(2)'})});
    socket.send(JSON.stringify({type:audio.paused?'play':'pause',seek_time:audio.currentTime||0}));
};
document.getElementById('stop-btn')?.addEventListener('click',()=>{
    logListenSession();
    socket?.readyState===WebSocket.OPEN&&socket.send(JSON.stringify({type:'stop'}));
});
document.getElementById('next-btn')?.addEventListener('click',()=>{
    if(!socket||socket.readyState!==WebSocket.OPEN) return;
    gsap.to('#next-btn',{x:5,duration:.15,yoyo:true,repeat:1});
    logListenSession();
    if(autoplayEnabled) fetchAutoplayNext();
    else socket.send(JSON.stringify({type:'skip'}));
});
document.getElementById('prev-btn')?.addEventListener('click',()=>{
    gsap.to('#prev-btn',{x:-5,duration:.15,yoyo:true,repeat:1});
    if(audio.currentTime>3){
        audio.currentTime=0;
        socket?.readyState===WebSocket.OPEN&&socket.send(JSON.stringify({type:'seek',seek_time:0}));
    } else {
        socket?.readyState===WebSocket.OPEN&&socket.send(JSON.stringify({type:'skip'}));
    }
});
document.getElementById('repeat-btn')?.addEventListener('click',()=>{
    repeatMode=!repeatMode;
    const btn=document.getElementById('repeat-btn');
    btn.classList.toggle('active',repeatMode);
    btn.style.color=repeatMode?'var(--accent)':'';
    gsap.from(btn,{scale:.8,duration:.2,ease:'back.out(2)'});
    showToast(repeatMode?'🔁 Repeat ON':'🔁 Repeat OFF');
});
document.getElementById('shuffle-btn')?.addEventListener('click',()=>{
    shuffleMode=!shuffleMode;
    const btn=document.getElementById('shuffle-btn');
    btn.classList.toggle('active',shuffleMode);
    btn.style.color=shuffleMode?'var(--accent)':'';
    gsap.from(btn,{scale:.8,duration:.2,ease:'back.out(2)'});
    showToast(shuffleMode?'🔀 Shuffle ON':'🔀 Shuffle OFF');
});

function seekForward(s){const t=Math.min(audio.currentTime+s,currentDurationSec||Infinity);audio.currentTime=t;socket?.readyState===WebSocket.OPEN&&socket.send(JSON.stringify({type:'seek',seek_time:t}));updateProgressUI(t,currentDurationSec);}
function seekBackward(s){const t=Math.max(0,audio.currentTime-s);audio.currentTime=t;socket?.readyState===WebSocket.OPEN&&socket.send(JSON.stringify({type:'seek',seek_time:t}));updateProgressUI(t,currentDurationSec);}

document.getElementById('fav-btn')?.addEventListener('click',saveFavorite);

// ══════════════════════════════════════════════════════════
//  AUTOPLAY UI
// ══════════════════════════════════════════════════════════
async function onAutoplayToggle(){
    const toggle=document.getElementById('autoplay-toggle');
    autoplayEnabled=toggle.checked;
    document.getElementById('autoplay-query-wrap').style.display=autoplayEnabled?'block':'none';
    if(!autoplayEnabled){
        await fetch(`/autoplay/set?chat_id=${roomChatId}&enabled=false`,{method:'POST'});
        document.getElementById('autoplay-indicator').style.display='none';
        showToast('⏹ Autoplay OFF');
    }
}
async function saveAutoplay(){
    const q=document.getElementById('autoplay-query-inp').value.trim();
    if(!q){showToast('❌ Enter a seed query');return;}
    autoplayQuery=q;autoplayEnabled=true;
    await fetch(`/autoplay/set?chat_id=${roomChatId}&enabled=true&query=${encodeURIComponent(q)}`,{method:'POST'});
    document.getElementById('autoplay-indicator').style.display='flex';
    document.getElementById('autoplay-label').textContent='Autoplay: '+q;
    showToast('✅ Autoplay ON: '+q.slice(0,20));
}
function toggleAutoplayUI(){
    autoplayEnabled=false;
    document.getElementById('autoplay-toggle').checked=false;
    document.getElementById('autoplay-query-wrap').style.display='none';
    document.getElementById('autoplay-indicator').style.display='none';
    fetch(`/autoplay/set?chat_id=${roomChatId}&enabled=false`,{method:'POST'});
    showToast('⏹ Autoplay OFF');
}

// ══════════════════════════════════════════════════════════
//  PROFILE — FULL POWERFUL
// ══════════════════════════════════════════════════════════
async function loadProfile(){
    if(!userId) return;
    try{
        const r=await fetch(`/profile?user_id=${userId}`);
        if(!r.ok) return;
        profileData=await r.json();
        renderProfile(profileData);
    }catch(e){console.error('[profile]',e);}
}

function renderProfile(d){
    // Apply theme color
    if(d.theme_color) applyThemeColor(d.theme_color);

    // Stats
    const totalMin=Math.floor((d.total_seconds||0)/60);
    document.getElementById('stat-songs').textContent=d.total_songs||0;
    document.getElementById('stat-time').textContent=totalMin<60?totalMin+'m':~~(totalMin/60)+'h '+(totalMin%60)+'m';
    document.getElementById('stat-rooms').textContent=d.rooms_joined||0;
    document.getElementById('stat-streak').textContent=d.streak||0;
    document.getElementById('streak-val').textContent=d.streak||0;

    // Bio
    const bioEl=document.getElementById('profile-bio');
    if(bioEl) bioEl.textContent=d.bio||'Tap to add bio...';

    // Badges
    renderBadges(d.badges||[]);

    // Weekly Chart
    renderWeeklyChart(d.weekly_hours||[0,0,0,0,0,0,0]);

    // Mood
    renderMood(d.mood||{});

    // Top Artists
    renderTopArtists(d.top_artists||[]);

    // Most Played
    renderMostPlayed(d.most_played||[]);

    // Friends
    renderFriends(d.friends||[]);

    // Room History
    renderRoomHistory(d.room_history||[]);

    // Autoplay
    const ap=d.autoplay;
    if(ap!==undefined){
        autoplayEnabled=!!ap;
        const tog=document.getElementById('autoplay-toggle');
        if(tog) tog.checked=autoplayEnabled;
        if(autoplayEnabled){
            document.getElementById('autoplay-query-wrap').style.display='block';
            document.getElementById('autoplay-query-inp').value=d.autoplay_query||'';
        }
    }
}

// BADGES
const BADGE_DEFS=[
    {id:'first_song', icon:'🎵', name:'First Song',   desc:'Played your first song'},
    {id:'night_owl',  icon:'🦉', name:'Night Owl',    desc:'Listened after midnight 3x'},
    {id:'bass_head',  icon:'🔊', name:'Bass Head',    desc:'Used bass boost 10+ times'},
    {id:'speed_runner',icon:'⚡',name:'Speed Runner', desc:'Used 2× speed 5+ times'},
    {id:'century',    icon:'💯', name:'100 Songs',    desc:'Listened to 100 songs'},
    {id:'streak_7',   icon:'🔥', name:'7-Day Streak', desc:'Listened 7 days in a row'},
    {id:'first_join', icon:'🥇', name:'First to Join',desc:'First in the room'},
    {id:'room_king',  icon:'👑', name:'Room King',    desc:'Most time in a room'},
];
function renderBadges(earned){
    const el=document.getElementById('badges-row');
    if(!el) return;
    const earnedSet=new Set(earned);
    el.innerHTML=BADGE_DEFS.map(b=>`
        <div class="badge-item ${earnedSet.has(b.id)?'earned':'locked'}">
            <div class="badge-icon">${b.icon}</div>
            <div class="badge-name">${b.name}</div>
            <div class="badge-desc">${b.desc}</div>
        </div>`).join('');
    document.getElementById('badges-card').style.display='block';
    gsap.from('.badge-item',{scale:.8,opacity:0,stagger:.05,duration:.3,ease:'back.out(2)',delay:.2});
}

// WEEKLY CHART
function renderWeeklyChart(hours){
    const el=document.getElementById('weekly-chart');
    if(!el) return;
    const maxH=Math.max(...hours,.01);
    const today=new Date().getDay(); // 0=Sun → remap to Mon=0
    const todayIdx=(today+6)%7;
    el.innerHTML=hours.map((h,i)=>`
        <div class="wc-bar-wrap">
            <div class="wc-bar${i===todayIdx?' today':''}" style="height:${(h/maxH)*60}px;">
                ${h>0?`<span class="wc-val">${h.toFixed(1)}h</span>`:''}
            </div>
        </div>`).join('');
    gsap.from('.wc-bar',{height:0,duration:.5,stagger:.07,ease:'back.out(1.5)',delay:.3});
}

// MOOD
function renderMood(mood){
    const el=document.getElementById('mood-section');
    if(!el) return;
    const items=[
        {icon:'🎸',label:'Bass Sessions', val:mood.bass_uses||0, max:50, color:'#ff9500'},
        {icon:'⚡',label:'Speed Sessions',val:mood.speed_uses||0,max:30, color:'#af52de'},
        {icon:'🌙',label:'Night Listens', val:mood.night_listens||0,max:30,color:'#007aff'},
        {icon:'🎵',label:'Songs Requested',val:mood.songs_requested||0,max:200,color:'#34c759'},
    ];
    el.innerHTML=items.map(it=>`
        <div class="mood-item">
            <div class="mood-icon">${it.icon}</div>
            <div class="mood-label">${it.label}</div>
            <div class="mood-val">${it.val}</div>
            <div class="mood-bar"><div class="mood-bar-fill" style="width:${Math.min((it.val/it.max)*100,100)}%;background:${it.color};"></div></div>
        </div>`).join('');
    gsap.from('.mood-item',{y:10,opacity:0,stagger:.06,duration:.3,ease:'power2.out',delay:.2});
}

// TOP ARTISTS
function renderTopArtists(artists){
    const card=document.getElementById('top-artists-card');
    const el  =document.getElementById('top-artists-list');
    if(!el||!card) return;
    if(!artists.length){card.style.display='none';return;}
    card.style.display='block';
    const maxC=artists[0]?.count||1;
    const ranks=['gold','silver','bronze'];
    el.innerHTML=artists.slice(0,5).map((a,i)=>`
        <div class="artist-item">
            <div class="artist-rank ${ranks[i]||''}">${i+1}</div>
            <div class="artist-info">
                <div class="artist-name">${escHtml(a.name||'Unknown')}</div>
                <div class="artist-count">${a.count} plays</div>
                <div class="artist-bar"><div class="artist-bar-fill" style="width:${(a.count/maxC)*100}%"></div></div>
            </div>
        </div>`).join('');
}

// MOST PLAYED
function renderMostPlayed(songs){
    const card=document.getElementById('most-played-card');
    const el  =document.getElementById('most-played-list');
    if(!el||!card) return;
    if(!songs.length){card.style.display='none';return;}
    card.style.display='block';
    el.innerHTML=songs.slice(0,7).map((s,i)=>`
        <div class="mp-item">
            <div class="mp-num">${i+1}</div>
            <div class="mp-title">${escHtml(s.title||'Unknown')}</div>
            <div class="mp-count">×${s.count}</div>
        </div>`).join('');
}

// FRIENDS
function renderFriends(friends){
    const el=document.getElementById('friends-list');
    if(!el) return;
    if(!friends.length){el.innerHTML='<p style="font-size:13px;color:var(--text3);">No friends yet. Add friends by user ID!</p>';return;}
    el.innerHTML=friends.map(f=>{
        const [c1,c2]=getAvatarColors(f.name||'');
        const initial=(f.name||'?')[0].toUpperCase();
        return`<div class="friend-item">
            <div class="friend-av" style="background:linear-gradient(135deg,${c1},${c2})">
                ${initial}
                ${f.online?'<div class="friend-online-dot"></div>':''}
            </div>
            <div class="friend-info">
                <div class="friend-name">${escHtml(f.name||'Unknown')}</div>
                <div class="friend-status">${f.online?'🟢 Online':'⚫ Offline'}</div>
            </div>
            <button class="friend-remove" onclick="removeFriend(${f.id})" title="Remove"><i class="fas fa-xmark"></i></button>
        </div>`;
    }).join('');
}

// ROOM HISTORY
function renderRoomHistory(history){
    const card=document.getElementById('room-history-card');
    const el  =document.getElementById('room-history-list');
    if(!el||!card) return;
    if(!history.length){card.style.display='none';return;}
    card.style.display='block';
    el.innerHTML=history.slice(-6).reverse().map(r=>`
        <div class="rh-item">
            <div class="rh-icon"><i class="fas fa-music"></i></div>
            <div class="rh-info">
                <div class="rh-name">${escHtml(r.name||'Group #'+r.chat_id)}</div>
                <div class="rh-time">${r.ts?r.ts.slice(0,10):''}</div>
            </div>
        </div>`).join('');
}

// Bio edit
function editBio(){
    const el=document.getElementById('profile-bio');
    if(!el) return;
    el.contentEditable='true';
    el.focus();
    el.onblur=()=>{
        el.contentEditable='false';
        const bio=el.textContent.slice(0,120);
        fetch(`/profile/update?user_id=${userId}&bio=${encodeURIComponent(bio)}`,{method:'POST'}).catch(()=>{});
        showToast('✅ Bio saved!');
    };
}

// Friends
function showAddFriendSheet(){
    document.getElementById('add-friend-sheet').style.display='block';
    document.getElementById('sheet-overlay').style.display='block';
    gsap.from('#add-friend-sheet',{y:100,opacity:0,duration:.35,ease:'back.out(1.5)'});
}
function closeSheets(){
    document.getElementById('add-friend-sheet').style.display='none';
    document.getElementById('sheet-overlay').style.display='none';
}
async function addFriend(){
    const fid =parseInt(document.getElementById('friend-id-inp').value)||0;
    const fname=document.getElementById('friend-name-inp').value.trim();
    if(!fid||!fname){showToast('❌ Enter ID and name');return;}
    const r=await fetch(`/friends/add?user_id=${userId}&friend_id=${fid}&friend_name=${encodeURIComponent(fname)}`,{method:'POST'});
    if(r.ok){showToast('✅ Friend added!');closeSheets();loadProfile();}
    else showToast('❌ Could not add friend');
}
async function removeFriend(fid){
    await fetch(`/friends/remove?user_id=${userId}&friend_id=${fid}`,{method:'POST'});
    showToast('Friend removed');
    loadProfile();
}

function refreshProfileUI(){
    document.getElementById('profile-name').textContent=username;
    document.getElementById('profile-handle').textContent=userHandle?('@'+userHandle):'';
    const av=document.getElementById('profile-avatar');
    if(userPhoto){
        av.innerHTML=`<img src="${userPhoto}" style="width:100%;height:100%;border-radius:50%;object-fit:cover;" onerror="this.remove()">`;
    } else {
        const t=document.getElementById('profile-av-text');
        if(t) t.textContent=initials;
    }
    document.getElementById('np-title').textContent=currentSongTitle||'Nothing Playing';
}

// ══════════════════════════════════════════════════════════
//  LOG LISTEN SESSION
// ══════════════════════════════════════════════════════════
async function logListenSession(){
    if(!userId||!currentSongTitle||sessionSeconds<5) return;
    const dur=sessionSeconds;
    sessionSeconds=0;
    const artist=currentSongTitle.split(' - ')[0]||currentSongTitle;
    try{
        await fetch(`/profile/log_session?user_id=${userId}&song_title=${encodeURIComponent(currentSongTitle)}&artist=${encodeURIComponent(artist)}&duration_sec=${dur}&bass_level=${currentBassLevel}&speed=${currentSpeed}&chat_id=${roomChatId}`,{method:'POST'});
    }catch{}
}

// ══════════════════════════════════════════════════════════
//  NOTIFICATIONS POLLER
// ══════════════════════════════════════════════════════════
function startNotifPoller(){
    if(!userId) return;
    setInterval(async()=>{
        try{
            const r=await fetch(`/notifications?user_id=${userId}`);
            const d=await r.json();
            const notifs=d.notifications||[];
            if(notifs.length>0){
                document.getElementById('notif-badge').style.display='block';
                const card=document.getElementById('notif-card');
                const el  =document.getElementById('notif-list');
                if(card&&el){
                    card.style.display='block';
                    el.innerHTML=notifs.map(n=>`
                        <div class="notif-item">
                            <div class="notif-dot"></div>
                            <div>
                                <div class="notif-msg">${escHtml(n.message||'')}</div>
                                <div class="notif-ts">${n.ts?.slice(11,16)||''}</div>
                            </div>
                        </div>`).join('');
                    // Show last notif as toast
                    showToast('🔔 '+notifs[notifs.length-1].message);
                }
            }
        }catch{}
    },10000);
}

// ══════════════════════════════════════════════════════════
//  FAVORITES
// ══════════════════════════════════════════════════════════
async function loadFavorites(){
    if(!userId) return;
    try{
        const r=await fetch(`/favorites?user_id=${userId}`);
        if(r.ok){const d=await r.json();favoriteSongs=d.favorites||[];renderFavoritesList();}
    }catch{}
}
async function saveFavorite(){
    if(!currentSongLink||!userId) return;
    const btn=document.getElementById('fav-btn');
    await fetch(`/favorites?user_id=${userId}`,{method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({link:currentSongLink,title:currentSongTitle,thumbnail:currentThumbUrl,duration_sec:currentDurationSec})});
    btn?.classList.add('active');
    gsap.to(btn,{scale:1.3,duration:.15,ease:'back.out(3)',onComplete:()=>gsap.to(btn,{scale:1,duration:.2})});
    showToast('❤️ Saved to Favorites!');
    await loadFavorites();
}
async function queueFavorite(song){
    showToast('⏳ Adding to queue...');
    const r=await fetch(`/queue_favorite?link=${encodeURIComponent(song.link)}&title=${encodeURIComponent(song.title||'')}&duration=${encodeURIComponent(formatSec(song.duration_sec||0))}&chat_id=${roomChatId}&user_id=${userId}`,{method:'POST'});
    showToast(r.ok?'✅ Added to queue!':'❌ Could not add');
}
function renderFavoritesList(){
    const el =document.getElementById('favorites-list');
    const sec=document.getElementById('favorites-section');
    if(!el||!sec) return;
    if(!favoriteSongs.length){sec.style.display='none';return;}
    sec.style.display='block';
    el.innerHTML=favoriteSongs.map(s=>`
        <div class="fav-item">
            ${s.thumbnail?`<img class="fav-thumb" src="${s.thumbnail}" onerror="this.style.display='none'" alt="">`
            :`<div class="fav-thumb-ph"><i class="fas fa-music"></i></div>`}
            <div class="fav-info">
                <div class="fav-title">${escHtml(s.title||'Unknown')}</div>
                <div class="fav-dur">${formatSec(s.duration_sec||0)}</div>
            </div>
            <button class="fav-queue-btn" onclick='queueFavorite(${JSON.stringify(s)})'><i class="fas fa-plus"></i> Queue</button>
        </div>`).join('');
}

// ══════════════════════════════════════════════════════════
//  AUTOPLAY OVERLAY (browser blocked)
// ══════════════════════════════════════════════════════════
function showAutoplayOverlay(){
    if(document.getElementById('autoplay-overlay')) return;
    const ov=document.createElement('div');
    ov.id='autoplay-overlay';
    ov.style.cssText='position:fixed;inset:0;z-index:900;background:rgba(0,0,0,.5);display:flex;align-items:center;justify-content:center;backdrop-filter:blur(10px);';
    ov.innerHTML=`<div style="background:var(--surface);border-radius:24px;padding:36px;text-align:center;box-shadow:var(--shadow-md);">
        <div style="font-size:48px;margin-bottom:12px">🎵</div>
        <div style="font-size:20px;font-weight:700;color:var(--text)">Tap to Play</div>
        <div style="font-size:14px;color:var(--text2);margin-top:6px">Tap anywhere to start audio</div>
    </div>`;
    document.body.appendChild(ov);
    gsap.from(ov,{opacity:0,duration:.3});
    ov.onclick=()=>{audio.play().catch(()=>{});gsap.to(ov,{opacity:0,duration:.2,onComplete:()=>ov.remove()});};
}

// ══════════════════════════════════════════════════════════
//  PLAY LINK
// ══════════════════════════════════════════════════════════
async function checkPlayLink(){
    if(!playLink) return;
    songTitleEl.textContent='⏳ Loading...';
    try{
        await fetch(`/play_song?link=${encodeURIComponent(playLink)}&title=${encodeURIComponent(playTitle)}&duration=${encodeURIComponent(playDuration)}&chat_id=${roomChatId}&user_id=${userId}`,{method:'POST'});
    }catch(e){songTitleEl.textContent='Error loading song';}
}

// ══════════════════════════════════════════════════════════
//  BASS (AudioContext)
// ══════════════════════════════════════════════════════════
let _audioCtx=null,_sourceNode=null,_bassFilter=null,_gainNode=null,_audioHooked=false;
let _currentBass={level:'off',gain:0,freq:60};
function _hookAudioContext(){
    if(_audioHooked||!audio.src) return;
    try{
        _audioCtx=new(window.AudioContext||window.webkitAudioContext)();
        _sourceNode=_audioCtx.createMediaElementSource(audio);
        _bassFilter=_audioCtx.createBiquadFilter();
        _bassFilter.type='lowshelf';_bassFilter.frequency.value=60;_bassFilter.gain.value=0;
        _gainNode=_audioCtx.createGain();_gainNode.gain.value=1;
        _sourceNode.connect(_bassFilter);_bassFilter.connect(_gainNode);_gainNode.connect(_audioCtx.destination);
        _audioHooked=true;
    }catch(e){console.warn('[Bass]',e);}
}
audio.addEventListener('play',()=>{if(!_audioHooked) _hookAudioContext();_audioCtx?.state==='suspended'&&_audioCtx.resume();},{passive:true});
function _applyBassConfig(cfg){
    _currentBass=cfg;
    if(_bassFilter){_bassFilter.frequency.value=cfg.freq||60;_bassFilter.gain.value=cfg.gain||0;}
    const level=cfg.level||'off';
    document.querySelectorAll('#bass-pills .ios-pill').forEach(b=>b.classList.toggle('active',b.dataset.bass===level));
}

// ══════════════════════════════════════════════════════════
//  CHAT
// ══════════════════════════════════════════════════════════
const avatarColors={};
const COLOR_POOL=[['#ff375f','#ff6b9d'],['#007aff','#34aadc'],['#34c759','#30b350'],['#ff9500','#ff6b00'],['#af52de','#7c3aed'],['#ff2d55','#ff375f']];
function getAvatarColors(name){if(!avatarColors[name]) avatarColors[name]=COLOR_POOL[Object.keys(avatarColors).length%COLOR_POOL.length];return avatarColors[name];}
function escHtml(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function getTimeStr(){const d=new Date();return d.getHours().toString().padStart(2,'0')+':'+d.getMinutes().toString().padStart(2,'0');}

function addChatMsg(text,fromName,isMine,subType,_,extra){
    subType=subType||'text';extra=extra||{};
    const[c1,c2]=getAvatarColors(fromName);
    const initial=(fromName.trim()[0]||'?').toUpperCase();
    const group=document.createElement('div');
    group.className='msg-group '+(isMine?'mine':'other');
    if(!isMine){
        const meta=document.createElement('div');
        meta.className='msg-meta';
        meta.innerHTML=`<div class="msg-av" style="background:linear-gradient(135deg,${c1},${c2})">${initial}</div><span class="msg-name">${escHtml(fromName)}</span>`;
        group.appendChild(meta);
    }
    const bubble=document.createElement('div');
    bubble.className='msg-bubble';
    if(subType==='voice') bubble.innerHTML=`<audio controls src="${escHtml(text)}" style="max-width:180px;vertical-align:middle"></audio>`;
    else if(subType==='media'){
        const mime=extra.mime||'',fname=extra.filename||'file';
        if(mime.startsWith('image/')) bubble.innerHTML=`<img src="${escHtml(text)}" style="max-width:200px;border-radius:10px;cursor:pointer;display:block" onclick="window.open(this.src,'_blank')">`;
        else if(mime.startsWith('video/')) bubble.innerHTML=`<video src="${escHtml(text)}" controls style="max-width:200px;border-radius:10px;display:block"></video>`;
        else if(mime.startsWith('audio/')) bubble.innerHTML=`<audio src="${escHtml(text)}" controls style="max-width:180px"></audio>`;
        else bubble.innerHTML=`<a href="${escHtml(text)}" download="${escHtml(fname)}" style="color:var(--accent);text-decoration:none">📎 ${escHtml(fname)}</a>`;
    } else bubble.textContent=text;
    group.appendChild(bubble);
    const timeEl=document.createElement('div');
    timeEl.className='msg-time';timeEl.textContent=getTimeStr();
    group.appendChild(timeEl);
    chatMsgsEl.appendChild(group);
    chatMsgsEl.scrollTop=chatMsgsEl.scrollHeight;
    if(currentTab!=='chat'&&!isMine) document.getElementById('chat-badge').style.display='block';
    gsap.from(group,{y:10,opacity:0,duration:.25,ease:'power2.out'});
}
function addSystemMsg(text){
    const el=document.createElement('div');el.className='chat-system';el.textContent=text;
    chatMsgsEl.appendChild(el);chatMsgsEl.scrollTop=chatMsgsEl.scrollHeight;
}

let _typingTimer=null;const _typingUsers=new Set();
function _showTypingBar(){const bar=document.getElementById('typing-bar');if(!bar) return;if(!_typingUsers.size){bar.textContent='';bar.style.display='none';return;}bar.textContent=[..._typingUsers].slice(0,2).join(', ')+(_typingUsers.size===1?' is':' are')+' typing...';bar.style.display='block';}
chatInput.addEventListener('input',()=>{if(!socket||socket.readyState!==WebSocket.OPEN) return;socket.send(JSON.stringify({type:'typing',username}));clearTimeout(_typingTimer);_typingTimer=setTimeout(()=>socket.send(JSON.stringify({type:'stop_typing',username})),2000);});
let _seenEl=document.getElementById('chat-seen-bar');
function _updateSeen(u){if(_seenEl) _seenEl.textContent='✓✓ Seen by '+u;setTimeout(()=>{if(_seenEl) _seenEl.textContent='';},4000);}
function sendChat(){const text=chatInput.value.trim();if(!text||!socket||socket.readyState!==WebSocket.OPEN) return;chatInput.value='';addChatMsg(text,username,true,'text');socket.send(JSON.stringify({type:'chat',message:text,username}));socket.send(JSON.stringify({type:'seen',username}));}
document.getElementById('chat-send-btn').onclick=sendChat;
chatInput.addEventListener('keydown',e=>{if(e.key==='Enter') sendChat();});

// Voice recorder
let _mediaRec=null,_voiceChunks=[];
const voiceBtn=document.getElementById('voice-btn');
if(voiceBtn){
    voiceBtn.addEventListener('mousedown',async()=>{if(!navigator.mediaDevices) return;const stream=await navigator.mediaDevices.getUserMedia({audio:true}).catch(()=>null);if(!stream) return;_voiceChunks=[];_mediaRec=new MediaRecorder(stream);_mediaRec.ondataavailable=e=>_voiceChunks.push(e.data);_mediaRec.onstop=()=>{const blob=new Blob(_voiceChunks,{type:'audio/webm'});const reader=new FileReader();reader.onload=()=>{if(!socket||socket.readyState!==WebSocket.OPEN) return;socket.send(JSON.stringify({type:'voice',username,data:reader.result}));addChatMsg(reader.result,username,true,'voice');};reader.readAsDataURL(blob);stream.getTracks().forEach(t=>t.stop());};_mediaRec.start();voiceBtn.classList.add('recording');});
    voiceBtn.addEventListener('mouseup',()=>{if(_mediaRec&&_mediaRec.state==='recording') _mediaRec.stop();voiceBtn.classList.remove('recording');});
}
const mediaBtn=document.getElementById('media-btn');
if(mediaBtn) mediaBtn.addEventListener('click',()=>{const inp=document.createElement('input');inp.type='file';inp.accept='image/*,video/*,audio/*,.pdf,.zip,.txt';inp.onchange=async()=>{const file=inp.files[0];if(!file) return;if(file.size>10*1024*1024){alert('Max 10MB');return;}const fd=new FormData();fd.append('file',file);fd.append('chat_id',roomChatId);fd.append('user_id',userId);fd.append('username',username);await fetch('/upload_media',{method:'POST',body:fd}).catch(()=>null);};inp.click();});

// ══════════════════════════════════════════════════════════
//  WEBRTC VOICE CALL — nav stays accessible
// ══════════════════════════════════════════════════════════
const callState={inCall:false,micEnabled:true,localStream:null,micPermission:null,
    peers:{},participants:{},gainNodes:{},audioCtx:null,callVolume:1,isMutedByAdmin:false,
    // ✅ Voice changer state
    voiceChanger:'none', pitchNode:null, sourceNode:null, processorNode:null, destStream:null,
};
const ICE={iceServers:[{urls:'stun:stun.l.google.com:19302'},{urls:'stun:stun1.l.google.com:19302'}]};

(async()=>{try{const p=await navigator.permissions.query({name:'microphone'});callState.micPermission=p.state;p.onchange=()=>callState.micPermission=p.state;}catch{callState.micPermission='prompt';}})();

async function _getMicStream(){
    if(callState.localStream?.getAudioTracks().some(t=>t.readyState==='live')) return callState.localStream;
    if(callState.micPermission==='denied'){showToast('🎤 Mic blocked. Allow in browser settings.');return null;}
    try{const s=await navigator.mediaDevices.getUserMedia({audio:true,video:false});callState.localStream=s;callState.micPermission='granted';return s;}
    catch{callState.micPermission='denied';showToast('🎤 Mic access denied.');return null;}
}

// ══════════════════════════════════════════════════════════
//  VOICE CHANGER — Real-time pitch/effect via WebAudio
// ══════════════════════════════════════════════════════════
const VOICE_PRESETS = {
    none:    { label: '🎤 Normal',   pitch: 1.0,  rate: 1.0  },
    baby:    { label: '👶 Baby',     pitch: 1.8,  rate: 0.9  },
    robot:   { label: '🤖 Robot',    pitch: 0.5,  rate: 1.0  },
    girl:    { label: '👧 Girl',     pitch: 1.5,  rate: 1.05 },
    boy:     { label: '👦 Boy',      pitch: 0.75, rate: 0.95 },
    demon:   { label: '😈 Demon',    pitch: 0.3,  rate: 0.8  },
    chipmunk:{ label: '🐿 Chipmunk', pitch: 2.0,  rate: 1.1  },
    deep:    { label: '🎙 Deep',     pitch: 0.6,  rate: 0.9  },
};

let _voiceCtx = null;
let _voiceSource = null;
let _voiceProcessor = null;
let _voiceDest = null;
let _currentVoice = 'none';
let _processedStream = null; // stream with effect applied — sent to peers

function _buildVoiceProcessor(rawStream) {
    // Stop old processor
    if (_voiceProcessor) {
        try { _voiceProcessor.disconnect(); } catch {}
        _voiceProcessor = null;
    }
    if (_voiceDest) {
        try { _voiceDest.disconnect(); } catch {}
    }
    if (_voiceCtx && _voiceCtx.state !== 'closed') {
        try { _voiceCtx.close(); } catch {}
    }

    const preset = VOICE_PRESETS[_currentVoice] || VOICE_PRESETS.none;

    if (_currentVoice === 'none') {
        // No effect — use raw stream
        _processedStream = rawStream;
        _updatePeersWithStream(rawStream);
        return;
    }

    // Build AudioContext pipeline: source → scriptProcessor (pitch shift) → dest
    _voiceCtx = new (window.AudioContext || window.webkitAudioContext)();
    _voiceSource = _voiceCtx.createMediaStreamSource(rawStream);
    _voiceDest   = _voiceCtx.createMediaStreamDestination();

    // Simple pitch shift using playbackRate on offline buffer chunks
    // We use a ScriptProcessorNode for real-time pitch via resampling
    const bufSize  = 4096;
    const pitch    = preset.pitch;
    _voiceProcessor = _voiceCtx.createScriptProcessor(bufSize, 1, 1);

    let inputBuffer  = new Float32Array(0);
    let outputBuffer = new Float32Array(0);
    let readPos      = 0;

    _voiceProcessor.onaudioprocess = (e) => {
        const input  = e.inputBuffer.getChannelData(0);
        const output = e.outputBuffer.getChannelData(0);
        const newIn  = new Float32Array(inputBuffer.length + input.length);
        newIn.set(inputBuffer);
        newIn.set(input, inputBuffer.length);
        inputBuffer = newIn;

        for (let i = 0; i < output.length; i++) {
            const srcIdx = Math.floor(readPos);
            if (srcIdx + 1 < inputBuffer.length) {
                const frac = readPos - srcIdx;
                output[i] = inputBuffer[srcIdx] * (1 - frac) + inputBuffer[srcIdx + 1] * frac;
            } else {
                output[i] = 0;
            }
            readPos += pitch;
        }

        // Trim consumed input
        const consumed = Math.floor(readPos);
        if (consumed > 0 && consumed < inputBuffer.length) {
            inputBuffer = inputBuffer.slice(consumed);
        } else if (consumed >= inputBuffer.length) {
            inputBuffer = new Float32Array(0);
        }
        readPos = readPos - Math.floor(readPos);
    };

    _voiceSource.connect(_voiceProcessor);
    _voiceProcessor.connect(_voiceDest);

    _processedStream = _voiceDest.stream;
    _updatePeersWithStream(_processedStream);
}

function _updatePeersWithStream(stream) {
    // Replace audio track in all existing peer connections
    const track = stream.getAudioTracks()[0];
    if (!track) return;
    for (const uid of Object.keys(callState.peers)) {
        const pc = callState.peers[uid]?.pc;
        if (!pc) continue;
        const sender = pc.getSenders().find(s => s.track?.kind === 'audio');
        if (sender) {
            sender.replaceTrack(track).catch(() => {});
        }
    }
    // Update local stream reference so new peers get the right track
    callState.localStream = stream;
}

function setVoiceChanger(type) {
    _currentVoice = type;
    callState.voiceChanger = type;

    // Update UI
    document.querySelectorAll('.vc-pill').forEach(b => {
        b.classList.toggle('active', b.dataset.voice === type);
    });

    // Apply
    if (callState.localStream) {
        const rawStream = type === 'none'
            ? callState.localStream
            : (callState._rawMicStream || callState.localStream);
        _buildVoiceProcessor(rawStream);
    }

    const label = VOICE_PRESETS[type]?.label || '🎤 Normal';
    showToast('Voice: ' + label);
}

async function joinCall(){
    if(callState.inCall){
        callOverlayVisible=true;
        const ov=document.getElementById('call-overlay');
        ov.style.display='block';
        gsap.fromTo(ov,{y:100,opacity:0},{y:0,opacity:1,duration:.35,ease:'back.out(1.5)'});
        return;
    }
    if(!socket||socket.readyState!==WebSocket.OPEN){alert('Join a room first!');return;}
    const stream=await _getMicStream();
    if(!stream) return;

    // ✅ Save raw mic stream for voice changer
    callState._rawMicStream = stream;
    _processedStream = stream; // default: no effect

    callState.micEnabled=true;callState.inCall=true;callOverlayVisible=true;
    callState.audioCtx=callState.audioCtx||new(window.AudioContext||window.webkitAudioContext)();
    callState.participants[userId]={username,muted:false,speaking:false};

    const ov=document.getElementById('call-overlay');
    ov.style.display='block';
    gsap.fromTo(ov,{y:100,opacity:0},{y:0,opacity:1,duration:.35,ease:'back.out(1.5)'});
    document.getElementById('call-sub').textContent='You are in the call 🟢';
    document.getElementById('call-badge').style.display='block';
    document.getElementById('nav-call').classList.add('call-active');
    _renderCallParticipants();
    socket.send(JSON.stringify({type:'call_join',username,user_id:userId}));
    _startSpeakingDetection(stream);
}

function leaveCall(){
    if(!callState.inCall) return;
    for(const uid of Object.keys(callState.peers)) _closePeer(uid);
    callState.localStream?.getTracks().forEach(t=>t.stop());callState.localStream=null;
    callState.audioCtx?.close().catch(()=>{});callState.audioCtx=null;
    callState.inCall=false;callState.peers={};callState.participants={};callState.gainNodes={};callState.micEnabled=true;callOverlayVisible=false;
    const ov=document.getElementById('call-overlay');
    gsap.to(ov,{y:60,opacity:0,duration:.25,ease:'power2.in',onComplete:()=>ov.style.display='none'});
    document.getElementById('call-badge').style.display='none';
    document.getElementById('nav-call').classList.remove('call-active');
    document.getElementById('call-participants').innerHTML='';
    document.getElementById('call-mic-btn').classList.remove('muted');
    document.getElementById('call-mic-icon').className='fas fa-microphone';
    socket?.readyState===WebSocket.OPEN&&socket.send(JSON.stringify({type:'call_leave',username,user_id:userId}));
}

function toggleMic(){
    if(!callState.localStream||callState.isMutedByAdmin) return;
    callState.micEnabled=!callState.micEnabled;
    callState.localStream.getAudioTracks().forEach(t=>t.enabled=callState.micEnabled);
    document.getElementById('call-mic-icon').className=callState.micEnabled?'fas fa-microphone':'fas fa-microphone-slash';
    document.getElementById('call-mic-btn').classList.toggle('muted',!callState.micEnabled);
    if(callState.participants[userId]) callState.participants[userId].muted=!callState.micEnabled;
    _renderCallParticipants();
    socket?.readyState===WebSocket.OPEN&&socket.send(JSON.stringify({type:'call_mute',target_id:userId,muted:!callState.micEnabled,username,user_id:userId}));
}
function setCallVolume(val){callState.callVolume=val;for(const uid of Object.keys(callState.gainNodes)) if(callState.gainNodes[uid]) callState.gainNodes[uid].gain.value=val;document.getElementById('call-vol-label').textContent=Math.round(val*100)+'%';}
function _createPeer(remoteId){
    if(callState.peers[remoteId]) return callState.peers[remoteId].pc;
    const pc=new RTCPeerConnection(ICE);callState.peers[remoteId]={pc,stream:null};
    // ✅ Use processed stream (voice changer output) for peers
    const streamToSend = _processedStream || callState.localStream;
    if(streamToSend) streamToSend.getTracks().forEach(t=>pc.addTrack(t, streamToSend));
    pc.onicecandidate=e=>{if(e.candidate&&socket?.readyState===WebSocket.OPEN) socket.send(JSON.stringify({type:'webrtc_ice',to_user_id:remoteId,candidate:e.candidate,username,user_id:userId}));};
    pc.ontrack=e=>{const rs=e.streams[0]||new MediaStream([e.track]);callState.peers[remoteId].stream=rs;_attachRemoteAudio(remoteId,rs);};
    pc.onconnectionstatechange=()=>{if(pc.connectionState==='failed'||pc.connectionState==='disconnected'){_closePeer(remoteId);delete callState.participants[remoteId];_renderCallParticipants();}};
    return pc;
}
function _attachRemoteAudio(remoteId,stream){
    if(!callState.audioCtx) return;
    const src=callState.audioCtx.createMediaStreamSource(stream);
    const gain=callState.audioCtx.createGain();gain.gain.value=callState.callVolume;
    src.connect(gain);gain.connect(callState.audioCtx.destination);callState.gainNodes[remoteId]=gain;
    let el=document.getElementById('call-audio-'+remoteId);
    if(!el){el=document.createElement('audio');el.id='call-audio-'+remoteId;el.autoplay=true;el.style.display='none';document.body.appendChild(el);}
    el.srcObject=stream;
}
function _closePeer(id){try{callState.peers[id]?.pc?.close();}catch{}delete callState.peers[id];delete callState.gainNodes[id];document.getElementById('call-audio-'+id)?.remove();}
async function _sendOffer(remoteId){
    const pc=_createPeer(remoteId);
    try{const offer=await pc.createOffer();await pc.setLocalDescription(offer);socket?.readyState===WebSocket.OPEN&&socket.send(JSON.stringify({type:'webrtc_offer',to_user_id:remoteId,sdp:pc.localDescription,username,user_id:userId}));}catch(e){console.error('[Call offer]',e);}
}
async function _handleCallSignal(data){
    const{type,from_user_id:fid,from_username:fname='Unknown'}=data;
    if(type==='call_join'){if(fid===userId) return;callState.participants[fid]={username:fname,muted:false,speaking:false};_renderCallParticipants();if(callState.inCall) await _sendOffer(fid);addSystemMsg(`📞 ${fname} joined the voice call`);document.getElementById('call-sub').textContent=Object.keys(callState.participants).length+' in call';}
    else if(type==='call_leave'){if(fid===userId) return;_closePeer(fid);delete callState.participants[fid];_renderCallParticipants();addSystemMsg(`📵 ${fname} left the voice call`);}
    else if(type==='call_mute'){const tid=data.target_id;if(callState.participants[tid]) callState.participants[tid].muted=data.muted;if(tid==userId&&data.is_admin_action&&data.muted){callState.isMutedByAdmin=true;callState.localStream?.getAudioTracks().forEach(t=>t.enabled=false);callState.micEnabled=false;document.getElementById('call-mic-icon').className='fas fa-microphone-slash';document.getElementById('call-mic-btn').classList.add('muted');addSystemMsg('🔇 You were muted by admin');}_renderCallParticipants();}
    else if(type==='webrtc_offer'){if(!callState.inCall||data.to_user_id!=userId) return;const pc=_createPeer(fid);try{await pc.setRemoteDescription(new RTCSessionDescription(data.sdp));const ans=await pc.createAnswer();await pc.setLocalDescription(ans);socket?.readyState===WebSocket.OPEN&&socket.send(JSON.stringify({type:'webrtc_answer',to_user_id:fid,sdp:pc.localDescription,username,user_id:userId}));}catch(e){console.error(e);}}
    else if(type==='webrtc_answer'){if(data.to_user_id!=userId) return;try{await callState.peers[fid]?.pc?.setRemoteDescription(new RTCSessionDescription(data.sdp));}catch(e){console.error(e);}}
    else if(type==='webrtc_ice'){if(data.to_user_id!=userId) return;try{await callState.peers[fid]?.pc?.addIceCandidate(new RTCIceCandidate(data.candidate));}catch(e){console.error(e);}}
}
function _startSpeakingDetection(stream){
    if(!callState.audioCtx) return;
    try{const src=callState.audioCtx.createMediaStreamSource(stream);const an=callState.audioCtx.createAnalyser();an.fftSize=256;src.connect(an);const buf=new Uint8Array(an.frequencyBinCount);setInterval(()=>{if(!callState.inCall) return;an.getByteFrequencyData(buf);const avg=buf.reduce((a,b)=>a+b,0)/buf.length;const sp=avg>12&&callState.micEnabled;if(callState.participants[userId]){const was=callState.participants[userId].speaking;callState.participants[userId].speaking=sp;if(was!==sp) _renderCallParticipants();}},200);}catch{}
}
function _renderCallParticipants(){
    const c=document.getElementById('call-participants');if(!c) return;
    c.innerHTML='';
    for(const[uid,info] of Object.entries(callState.participants)){
        const div=document.createElement('div');div.className='call-participant';
        const[c1,c2]=getAvatarColors(info.username||'');
        const init=(info.username||'?')[0].toUpperCase();
        const sp=info.speaking&&!info.muted;
        div.innerHTML=`<div class="call-av${sp?' speaking':''}${info.muted?' muted':''}" style="background:linear-gradient(135deg,${c1},${c2})">${init}</div><div class="call-p-name">${escHtml(info.username||'User')}</div>`;
        c.appendChild(div);
    }
}

// ══════════════════════════════════════════════════════════
//  TOAST
// ══════════════════════════════════════════════════════════
function showToast(text,dur=2500){
    let t=document.getElementById('toast-msg');
    if(!t){t=document.createElement('div');t.id='toast-msg';document.body.appendChild(t);}
    t.textContent=text;t.style.opacity='1';
    gsap.fromTo(t,{y:10,opacity:0},{y:0,opacity:1,duration:.3,ease:'power2.out'});
    clearTimeout(t._timer);t._timer=setTimeout(()=>gsap.to(t,{opacity:0,duration:.3}),dur);
}

// ══════════════════════════════════════════════════════════
//  UTILS
// ══════════════════════════════════════════════════════════
function formatTime(s){if(!s||isNaN(s)||s===Infinity||s<0) return'0:00';const t=Math.floor(s),m=Math.floor(t/60),sec=t%60;return`${m}:${sec.toString().padStart(2,'0')}`;}
function formatSec(sec){if(!sec||isNaN(sec)) return'';const m=Math.floor(sec/60),s=sec%60;return`${m}:${s.toString().padStart(2,'0')}`;}

// ══════════════════════════════════════════════════════════
//  INIT
// ══════════════════════════════════════════════════════════
showJoinScreen();
setInterval(()=>{if(currentTab==='profile') loadProfile();},30000);
setInterval(()=>{if(hasJoined&&isPlaying) sessionSeconds++;},1000);

(() => {
  const form = document.getElementById('ctChatForm');
  if (!form) return;
  const transcript = document.getElementById('ctChatHistory');
  const input = document.getElementById('ctChatQuestion');
  const status = document.getElementById('ctChatStatus');
  const submit = form.querySelector('[type=submit]');
  const clear = document.getElementById('ctChatClear');
  let history = [], busy = false;
  function line(role, content) {
    const node = document.createElement('div'); node.className = 'panel';
    const name = document.createElement('strong'); name.textContent = role;
    const text = document.createElement('p'); text.style.whiteSpace = 'pre-wrap'; text.style.overflowWrap='anywhere'; text.textContent = content;
    node.append(name,text); transcript.append(node); transcript.scrollTop=transcript.scrollHeight;
  }
  clear.addEventListener('click', () => { if (!busy) { history=[]; transcript.replaceChildren(); status.textContent='Chat cleared.'; } });
  form.addEventListener('submit', async (event) => {
    event.preventDefault(); if (busy) return;
    const question=input.value.trim(); if (!question || !document.getElementById('ctChatConsent').checked) return;
    const include_summary=document.getElementById('ctChatSummary').checked;
    busy=true; submit.disabled=true; clear.disabled=true; status.textContent='Requesting response…';
    line('You',question);
    try {
      const res=await fetch(form.dataset.url,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRFToken':document.querySelector('meta[name="csrf-token"]').content},body:JSON.stringify({question,history,consent:true,include_summary})});
      if (res.redirected) throw Error('Session expired. Sign in again.');
      const data=await res.json(); if (!res.ok) throw Error(data.error||'Request failed.');
      line('CarbonTrack AI',data.answer); history=[...history,{role:'user',content:question},{role:'assistant',content:data.answer.slice(0,2000)}].slice(-6); input.value=''; status.textContent='';
    } catch(e) { status.textContent=e.message||'Unable to connect.'; }
    finally { busy=false; submit.disabled=false; clear.disabled=false; }
  });
})();

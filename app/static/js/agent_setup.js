(() => {
  const form=document.getElementById('ctEnrollForm'); if(!form)return;
  const status=document.getElementById('ctEnrollStatus');
  const box=document.getElementById('ctTokenBox');
  const token=document.getElementById('ctEnrollmentToken');
  const submit=form.querySelector('[type=submit]');
  document.getElementById('ctCopyToken').addEventListener('click',async()=>{
    try { await navigator.clipboard.writeText(token.value); status.textContent='Token copied. Keep it private.'; }
    catch { token.focus(); token.select(); status.textContent='Select and copy the token manually.'; }
  });
  document.getElementById('ctHideToken').addEventListener('click',()=>{token.value='';box.hidden=true;status.textContent='Token cleared from this page.';});
  form.addEventListener('submit',async(e)=>{
    e.preventDefault(); if(!box.hidden){status.textContent='Copy and clear the previous token first.';return;}
    submit.disabled=true;status.textContent='Enrolling…';
    try {
      const res=await fetch(form.dataset.url,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRFToken':document.querySelector('meta[name="csrf-token"]').content},body:JSON.stringify({name:document.getElementById('ctEnrollName').value.trim(),platform:document.getElementById('ctEnrollPlatform').value})});
      if(res.redirected)throw Error('Sign in again.'); const data=await res.json();
      if(!res.ok)throw Error(data.error||'Enrollment failed.');
      token.value=data.token;box.hidden=false;status.textContent='Enrolled. Copy the token before leaving this page.';
    }catch(e){status.textContent=e.message||'Enrollment failed.';}finally{submit.disabled=false;}
  });
})();

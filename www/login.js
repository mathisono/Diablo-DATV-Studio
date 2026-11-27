'use strict';
document.querySelector('#login').addEventListener('submit', async event => {
  event.preventDefault();
  const button=event.target.querySelector('button'), input=document.querySelector('#password'), message=document.querySelector('#message');
  const bytes=new TextEncoder().encode(input.value).length;
  if (bytes<8 || bytes>128) {message.textContent='Password is too short or too long.';return;}
  button.disabled=true;message.textContent='Signing in…';
  try {
    const response=await fetch('/api/auth/login', {method:'POST',headers:{'Content-Type':'application/json','X-Portsdown-Control':'1'},body:JSON.stringify({password:input.value})});
    input.value='';
    const data=await response.json();
    if (!response.ok) throw Error(data.error || 'Sign-in failed');
    location.replace('/');
  } catch(error) {message.textContent=error.message;} finally {button.disabled=false;}
});

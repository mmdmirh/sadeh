document.addEventListener('DOMContentLoaded', () => {
  // DOM elements
  const promptInput = document.getElementById('prompt');
  const chatBody = document.getElementById('chat-body');
  const sendButton = document.getElementById('send-btn');
  const conversationId = document.getElementById('conversation_id')?.value;
  const fileUpload = document.getElementById('file-upload');
  const modelSelect = document.getElementById('model-select');
  const newChatForm = document.querySelector('.new-chat-form');
  const newChatModelInput = document.querySelector('input[name="model"]', newChatForm);
  const sidebar = document.getElementById('sidebar');
  const toggleSidebar = document.getElementById('toggle-sidebar');

  // Voice recording
  const voiceRecordButton = document.getElementById('voice-record-btn');
  const recordingIndicator = document.getElementById('recording-indicator');
  const recordingTimer = document.getElementById('recording-timer');
  let mediaRecorder, audioChunks = [], recordingInterval;

  // AI streaming vars
  let isAiResponding = false;
  let currentAbortController;
  let aiQueue = [], aiTimer, aiBubble, aiDone;

  // Helpers
  function scrollToBottom() {
    chatBody.scrollTop = chatBody.scrollHeight;
  }
  function escapeHTML(str) {
    return str.replace(/[&<>'"]/g, tag => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[tag]));
  }
  function renderMarkdown(text) {
    // code fences
    text = text.replace(/```(\w+)?\n([\s\S]*?)```/g,(m,lang,code)=>{
      return `<pre><code class="language-${lang||''}">${escapeHTML(code)}</code></pre>`;
    });
    // bold
    text = text.replace(/\*\*(.*?)\*\*/g,'<strong>$1</strong>');
    // italics
    text = text.replace(/\*(.*?)\*/g,'<em>$1</em>');
    return text.replace(/\n/g,'<br>');
  }

  function toggleSendStop(showStop) {
    if(!sendButton) return;
    if(showStop) {
      sendButton.innerHTML = 'Stop';
      sendButton.classList.add('stop');
      sendButton.onclick = abortResponse;
    } else {
      sendButton.innerHTML = 'Send';
      sendButton.classList.remove('stop');
      sendButton.onclick = sendMessage;
    }
  }
  function abortResponse() {
    currentAbortController?.abort();
    finalize();
  }
  function finalize() {
    isAiResponding = false; promptInput.disabled = false;
    toggleSendStop(false); aiDone = true; aiQueue=[]; aiTimer=null; aiBubble=null;
  }

  // Animated AI output
  function animateAI() {
    if(aiTimer) return;
    aiTimer = setInterval(()=>{
      if(aiQueue.length>0 && aiBubble) {
        aiBubble.textContent += aiQueue.shift(); scrollToBottom();
      } else if(aiDone && aiQueue.length===0) {
        clearInterval(aiTimer); aiTimer=null;
        aiBubble.innerHTML = renderMarkdown(aiBubble.textContent);
      }
    },30);
  }

  // Create thinking placeholder
  function createThinking() {
    const div = document.createElement('div'); div.className='message ai-message thinking';
    div.innerHTML = `<div class="message-content"><div class="message-inner"><div class="message-avatar ai-avatar">A</div><div class="message-bubble"><div class="ai-content"></div></div></div></div>`;
    document.querySelector('.messages-container').appendChild(div); scrollToBottom();
    return div;
  }

  // Add to UI
  function addMessage(sender,content) {
    const container = document.querySelector('.messages-container');
    const div = document.createElement('div'); div.className=`message ${sender}-message`;
    const inner = `
      <div class="message-content"><div class="message-inner">
        <div class="message-avatar ${sender}-avatar">${sender==='user'?''+escapeHTML(content[0]||''):''}</div>
        <div class="message-bubble">${sender==='user'?escapeHTML(content):'<div class="ai-content">'+renderMarkdown(content)+'</div>'}</div>
      </div></div>`;
    div.innerHTML = inner; container.appendChild(div); scrollToBottom();
  }

  // Send
  function sendMessage() {
    if(isAiResponding) return;
    const text = promptInput.value.trim(); if(!text) return;
    addMessage('user',text);
    promptInput.value=''; promptInput.style.height='auto';
    const thinkDiv = createThinking();
    const bubble = thinkDiv.querySelector('.ai-content');
    aiBubble = bubble; aiDone=false;
    isAiResponding=true; toggleSendStop(true); promptInput.disabled=true;

    const form = new FormData(); form.append('conversation_id',conversationId); form.append('prompt',text);
    currentAbortController = new AbortController();
    fetch('/call_model',{method:'POST',body:form,signal:currentAbortController.signal})
      .then(res=>{if(!res.ok) throw Error(res.status); return res.body.getReader();})
      .then(reader=>{
        const dec=new TextDecoder(); function read({done,value}){
          if(done) { aiDone=true; animateAI(); finalize(); return; }
          const chunk=dec.decode(value,true);
          chunk.split('\n').forEach(line=>{
            if(line.startsWith('data: ')){
              try{const d=JSON.parse(line.slice(6)); if(d.text) for(const c of d.text) aiQueue.push(c);}catch{} }
          }); animateAI(); reader.read().then(read);
        }
        reader.read().then(read);
      })
      .catch(e=>{bubble.innerHTML=`<span class="error">${escapeHTML(e.message)}</span>`; finalize();});
  }

  // Auto-expand textarea
  promptInput.addEventListener('input',e=>{e.target.style.height='auto'; e.target.style.height=e.target.scrollHeight+'px';});
  promptInput.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault(); sendMessage();}});
  sendButton.onclick = sendMessage;

  // Sidebar toggle
  toggleSidebar?.addEventListener('click',()=>sidebar.classList.toggle('open'));

  // New chat form model sync
  modelSelect?.addEventListener('change',e=>newChatModelInput.value=e.target.value);
});

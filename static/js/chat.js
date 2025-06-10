document.addEventListener('DOMContentLoaded', () => {
  // DOM elements
  const promptInput = document.getElementById('prompt');
  const chatBody = document.getElementById('chat-body');
  const sendButton = document.getElementById('send-btn');
  const conversationId = document.getElementById('conversation_id')?.value;
  // const fileUpload = document.getElementById('file-upload'); // Retain if used, ensure it's handled
  const modelSelect = document.getElementById('model-select');
  const newChatForm = document.querySelector('.new-chat-form');
  const newChatModelInput = newChatForm ? newChatForm.querySelector('input[name="model"]') : null;
  const sidebar = document.getElementById('sidebar');
  const toggleSidebar = document.getElementById('toggle-sidebar');

  // Voice recording (ensure these elements exist or add null checks)
  // const voiceRecordButton = document.getElementById('voice-record-btn');
  // const recordingIndicator = document.getElementById('recording-indicator');
  // const recordingTimer = document.getElementById('recording-timer');
  // let mediaRecorder, audioChunks = [], recordingInterval;

  // AI streaming vars
  let isAiResponding = false;
  let currentAbortController;
  let aiQueue = [], aiTimer, aiDone;
  let currentThinkingBubbleDiv = null;

  // SVG Icons for the send/stop button
  const sendIconHTML = '<svg fill="none" stroke="currentColor" viewBox="0 0 24 24" width="20" height="20"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"/></svg>';
  const stopIconHTML = '<svg fill="currentColor" viewBox="0 0 24 24" width="20" height="20"><path d="M12,2A10,10 0 0,0 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12A10,10 0 0,0 12,2Z M9,9H15V15H9V9Z" /></svg>';

  // Helpers
  function scrollToBottom() {
    if (chatBody) {
        chatBody.scrollTop = chatBody.scrollHeight;
    }
  }

  function escapeHTML(str) {
    if (typeof str !== 'string') return '';
    return str.replace(/[&<>'\"]/g, tag => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[tag]));
  }

  function renderMarkdown(text) {
    if (typeof text !== 'string') text = String(text);
    // Basic code fences (does not highlight)
    text = text.replace(/```(\w+)?\n([\s\S]*?)```/g, (m, lang, code) => {
      return `<pre><code class="language-${lang || ''}">${escapeHTML(code)}</code></pre>`;
    });
    // Bold
    text = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    // Italics
    text = text.replace(/(?<!\*)\*(?!\*|_)(.*?)(?<!_)\*(?!\*)/g, '<em>$1</em>'); // More specific italics
    // Newlines
    return text.replace(/\n/g, '<br>');
  }

  function simplifyErrorMessage(rawMessage) {
    if (typeof rawMessage !== 'string') rawMessage = String(rawMessage);

    if (rawMessage.toLowerCase().includes('failed to fetch') || rawMessage.toLowerCase().includes('networkerror')) {
        return '⚠️ Network error. Could not reach the server. Please check your connection and try again.';
    }
    if (rawMessage.match(/^\d{3}$/) || rawMessage.match(/HTTP error! Status: (\d{3})/)) {
        const codeMatch = rawMessage.match(/(\d{3})/);
        const code = codeMatch ? parseInt(codeMatch[1], 10) : parseInt(rawMessage, 10);
        if (code === 400) return '⚠️ Bad request. The server could not understand the request.';
        if (code === 401) return '⚠️ Unauthorized. Authentication failed or is required.';
        if (code === 403) return '⚠️ Forbidden. You do not have permission for this action.';
        if (code === 404) return '⚠️ Not found. The requested resource could not be found.';
        if (code === 429) return '⚠️ Too many requests. Please wait a moment and try again.';
        if (code >= 500) return `⚠️ Server error (${code}). Something went wrong on our end. Please try again later.`;
    }
    // For other errors, provide a generic message but include a snippet of the original if it's short
    const shortMessage = rawMessage.length < 100 ? rawMessage : rawMessage.substring(0, 100) + '...';
    return `⚠️ An unexpected error occurred: ${escapeHTML(shortMessage)}`;
  }

  function displayChatMessage(sender, content, isError = false, errorDetails = '') {
    const container = document.querySelector('.messages-container');
    if (!container) return null;

    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${sender}-message${isError ? ' error-message' : ''}`;

    let avatarHtml = '';
    if (sender === 'user') {
        // Use global current_user_username if available, otherwise default
        const userName = typeof current_user_username !== 'undefined' && current_user_username ? current_user_username : 'User';
        // const userInitial = userName[0]?.toUpperCase() || 'U'; // User initial not used in current SVG
        avatarHtml = `<div class="message-avatar user-avatar">
                        <svg class="user-avatar" width="32" height="32" viewBox="0 0 32 32" fill="none"><circle cx="16" cy="16" r="16" fill="#E5E7EB"/><path d="M16 16C18.2091 16 20 14.2091 20 12C20 9.79086 18.2091 8 16 8C13.7909 8 12 9.79086 12 12C12 14.2091 13.7909 16 16 16Z" fill="#6B7280"/><path d="M8 24C8 19.5817 11.5817 16 16 16C20.4183 16 24 19.5817 24 24" fill="#6B7280"/></svg>
                      </div>`;
    } else if (isError) {
        avatarHtml = `<div class="message-avatar error-avatar">
                        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor">
                            <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd" />
                        </svg>
                      </div>`;
    } else { // AI avatar
        avatarHtml = `<div class="message-avatar ai-avatar">
                        <svg width="32" height="32" viewBox="0 0 32 32" fill="none"><circle cx="16" cy="16" r="16" fill="#D1FAE5"/><path d="M16 16C18.2091 16 20 14.2091 20 12C20 9.79086 18.2091 8 16 8C13.7909 8 12 9.79086 12 12C12 14.2091 13.7909 16 16 16Z" fill="#10B981"/><path d="M8 24C8 19.5817 11.5817 16 16 16C20.4183 16 24 19.5817 24 24" fill="#10B981"/></svg>
                      </div>`;
    }

    let bubbleContentHtml = '';
    if (isError) {
        const userFriendlyMessage = simplifyErrorMessage(content);
        // Ensure errorDetails is a string for escapeHTML
        const detailsToDisplay = typeof errorDetails === 'string' ? errorDetails : JSON.stringify(errorDetails);
        bubbleContentHtml = `<div class="error-content">
                               <p class="error-summary">${escapeHTML(userFriendlyMessage)}</p>
                               ${errorDetails ? `
                               <div class="error-details-container">
                                   <button class="error-details-toggle">Show Details</button>
                                   <pre class="error-details-content" style="display: none;">${escapeHTML(detailsToDisplay)}</pre>
                               </div>` : ''}
                           </div>`;
    } else if (sender === 'user') {
        bubbleContentHtml = escapeHTML(content);
    } else { // AI content
        if (content === '' && !isError) { // Check for initial empty AI message
        bubbleContentHtml = `<div class="ai-content"><span class="thinking-indicator"><span>.</span><span>.</span><span>.</span></span></div>`;
    } else {
        bubbleContentHtml = `<div class="ai-content">${renderMarkdown(content)}</div>`; // Markdown for AI
    }
    }

    const innerHtml = `
        <div class="message-content">
            <div class="message-inner">
                ${avatarHtml}
                <div class="message-bubble${isError ? ' error-bubble' : ''}">
                    ${bubbleContentHtml}
                </div>
            </div>
        </div>`;
    messageDiv.innerHTML = innerHtml;
    container.appendChild(messageDiv);

    if (isError && errorDetails) {
        const toggleButton = messageDiv.querySelector('.error-details-toggle');
        const detailsContent = messageDiv.querySelector('.error-details-content');
        if (toggleButton && detailsContent) {
            toggleButton.addEventListener('click', (e) => {
                e.preventDefault();
                const isHidden = detailsContent.style.display === 'none';
                detailsContent.style.display = isHidden ? 'block' : 'none';
                toggleButton.textContent = isHidden ? 'Hide Details' : 'Show Details';
                scrollToBottom();
            });
        }
    }
    scrollToBottom();
    return messageDiv;
  }

  function toggleSendStop(showStop) {
    if (!sendButton) return;
    if (showStop) {
      sendButton.innerHTML = stopIconHTML;
      sendButton.title = "Stop generating";
      sendButton.onclick = abortResponse;
      sendButton.classList.add('stop-button'); 
      sendButton.classList.remove('send-btn-active'); 
    } else {
      sendButton.innerHTML = sendIconHTML;
      sendButton.title = "Send message";
      sendButton.onclick = sendMessage;
      sendButton.classList.remove('stop-button');
      sendButton.classList.add('send-btn-active'); 
    }
  }

  function abortResponse() {
    if (currentAbortController) {
      currentAbortController.abort(); // This will trigger catch in fetch or stop stream processing
    }
    // finalize() will be called by the fetch catch or stream abortion logic
  }

  function finalize() {
    isAiResponding = false;
    if (promptInput) promptInput.disabled = false;
    toggleSendStop(false);
    aiDone = true; 
    aiQueue = [];
    clearInterval(aiTimer); 
    aiTimer = null;
    
    // If a thinking bubble exists and is still marked as 'thinking', remove it.
    // Otherwise, it has become a proper message or error and should remain.
    if (currentThinkingBubbleDiv && currentThinkingBubbleDiv.classList.contains('thinking')) {
        currentThinkingBubbleDiv.remove();
    }
    currentThinkingBubbleDiv = null; // Always reset
  }

  let originalTitle = document.title;
  let isWindowActive = true;
  let unreadMessages = 0;

  window.addEventListener('focus', () => {
    isWindowActive = true;
    unreadMessages = 0; // Reset counter
    // Adding a slight delay to ensure this runs after any immediate message processing
    setTimeout(() => { document.title = originalTitle; }, 100);
  });

  window.addEventListener('blur', () => {
    isWindowActive = false;
  });

  // Function to update title with notification
  function showNotificationInTitle() {
    if (!isWindowActive) {
        unreadMessages++;
        document.title = `(${unreadMessages}) ${originalTitle}`;
    }
  }

  function animateAI() {
    if (aiTimer || !currentThinkingBubbleDiv || currentThinkingBubbleDiv.classList.contains('error-message')) {
        // Do not animate if already animating, no bubble, or it's an error bubble
        return;
    }

    const aiContentBubble = currentThinkingBubbleDiv.querySelector('.ai-content');
    if (!aiContentBubble) {
        finalize(); // Should not happen if bubble was created correctly
        return;
    }

    // Remove 'thinking' state as we are now populating content
    currentThinkingBubbleDiv.classList.remove('thinking');
    // Clear initial '...' or thinking indicator if it was textContent
    if (aiContentBubble.innerHTML.includes('<span class="thinking-indicator"></span>')) {
        aiContentBubble.innerHTML = ''; 
    }

    aiTimer = setInterval(() => {
      if (aiQueue.length > 0) {
        aiContentBubble.textContent += aiQueue.shift(); // Append text directly for performance
        scrollToBottom();
      } else if (aiDone) { 
        clearInterval(aiTimer);
        aiTimer = null;
        // Apply markdown to the accumulated text content
        if (aiContentBubble.textContent.trim() !== '') {
            aiContentBubble.innerHTML = renderMarkdown(aiContentBubble.textContent);
          showNotificationInTitle(); // Notify for new message
      } else if (!currentThinkingBubbleDiv.classList.contains('error-message')) {
            // If no content and not an error, remove the empty AI bubble
            currentThinkingBubbleDiv.remove();
            currentThinkingBubbleDiv = null; 
        }
        finalize(); 
      }
    }, 30); // Animation speed
  }
  
  async function sendMessage() {
    if (isAiResponding || !promptInput) return;
    const text = promptInput.value.trim();
    if (!text) return;
    
    // Check if there's a conversation selected
    const conversationId = document.getElementById('conversation_id')?.value;
    if (!conversationId) {
        // If no conversation is selected, show an error message
        displayChatMessage('ai', 'Please create a new conversation first before sending messages.', true);
        return;
    }

    displayChatMessage('user', text);
    promptInput.value = '';
    promptInput.style.height = 'auto'; // Reset height

    isAiResponding = true;
    promptInput.disabled = true;
    toggleSendStop(true);
    aiDone = false;
    aiQueue = [];

    // Create a thinking bubble
    if (currentThinkingBubbleDiv) currentThinkingBubbleDiv.remove(); // Remove any previous one
    currentThinkingBubbleDiv = displayChatMessage('ai', '', false); // Create with empty content initially
    if (currentThinkingBubbleDiv) {
        currentThinkingBubbleDiv.classList.add('thinking');
        const thinkingAICotentBubble = currentThinkingBubbleDiv.querySelector('.ai-content');
        if(thinkingAICotentBubble) thinkingAICotentBubble.innerHTML = '<span class="thinking-indicator"></span>'; // Visual indicator
    } else {
        console.error("Failed to create thinking bubble for AI response.");
        finalize(); // Critical failure, allow user to try again
        return;
    }

    const formData = new FormData();
    formData.append('conversation_id', conversationId);
    formData.append('prompt', text);
    if (modelSelect && modelSelect.value) {
        formData.append('model_name', modelSelect.value);
    }
    const csrfTokenInput = document.getElementById('csrf_token');
    if (csrfTokenInput && csrfTokenInput.value) {
        formData.append('csrf_token', csrfTokenInput.value);
    } else {
        console.warn('CSRF token input not found or empty. Request might fail.');
        // Optionally, display an error to the user here or prevent the request
    }

    currentAbortController = new AbortController();

    try {
      const response = await fetch('/call_model', {
        method: 'POST',
        body: formData,
        signal: currentAbortController.signal,
      });

      if (!response.ok) {
        let errorBody = null;
        try {
            errorBody = await response.json(); // Try to parse backend error
        } catch (e) { /* Not a JSON error response */ }
        
        const statusText = response.statusText || 'Unknown Error';
        const errorMessage = errorBody?.error || `HTTP error! Status: ${response.status}`;
        const errorDetails = errorBody?.details || (errorBody ? JSON.stringify(errorBody) : statusText);
        throw { name: 'HTTPError', message: errorMessage, details: errorDetails, status: response.status };
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();

      // Arrow function for processStream to maintain 'this' context if ever needed, though not currently
      const processStream = async ({ done, value }) => {
        if (currentAbortController.signal.aborted) {
            // Stream was aborted by user or error elsewhere
            aiDone = true; // Signal completion
            if (!aiTimer && currentThinkingBubbleDiv && !currentThinkingBubbleDiv.classList.contains('error-message')) animateAI(); // Finalize animation if it hasn't started
            else if (!currentThinkingBubbleDiv || currentThinkingBubbleDiv.classList.contains('error-message')) finalize();
            return;
        }

        if (done) {
          aiDone = true;
          if (!aiTimer && currentThinkingBubbleDiv && !currentThinkingBubbleDiv.classList.contains('error-message')) animateAI(); // Ensure animation runs to finalize content
          else if (!currentThinkingBubbleDiv || currentThinkingBubbleDiv.classList.contains('error-message')) finalize();
          return;
        }

        const chunk = decoder.decode(value, { stream: true });
        chunk.split('\n').forEach(line => {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              if (data.error) {
                if (currentThinkingBubbleDiv) currentThinkingBubbleDiv.remove();
                currentThinkingBubbleDiv = null;
                displayChatMessage('ai', data.error, true, data.error_details || data.error);
                currentAbortController.abort(); // Stop further processing
                finalize(); 
                return; // Exit forEach for this line
              }
              if (data.topic !== undefined) {
                updateTopicUI(data.topic);
              } else if (data.text) {
                aiQueue.push(data.text);
              }
            } catch (e) {
              console.error('Failed to parse SSE line JSON:', e, "Line:", line);
              if (currentThinkingBubbleDiv) currentThinkingBubbleDiv.remove();
              currentThinkingBubbleDiv = null;
              displayChatMessage('ai', 'Error processing data from server.', true, `Malformed data: ${line.substring(0,50)}... Details: ${e.message}`);
              currentAbortController.abort(); 
              finalize();
              return; // Exit forEach for this line
            }
          }
        });
        // Start animation if not already started and there's a bubble
        if (!aiTimer && currentThinkingBubbleDiv && !currentThinkingBubbleDiv.classList.contains('error-message')) animateAI();
        
        // Continue reading
        try {
            await reader.read().then(processStream);
        } catch (streamError) {
            if (currentAbortController.signal.aborted && streamError.name === 'AbortError') {
                // This is expected if aborted, finalize will handle it.
            } else {
                console.error('Stream reading error:', streamError);
                if (currentThinkingBubbleDiv) currentThinkingBubbleDiv.remove();
                currentThinkingBubbleDiv = null;
                displayChatMessage('ai', 'Error reading response from server.', true, streamError.message);
            }
            finalize(); // Finalize on any stream error
        }
      };

      await reader.read().then(processStream);

    } catch (error) {
      console.error('Fetch or processing error:', error);
      if (currentThinkingBubbleDiv) {
        currentThinkingBubbleDiv.remove(); // Remove thinking bubble
        currentThinkingBubbleDiv = null;
      }
      // Use error.message and error.details if they exist (from custom HTTPError)
      const message = error.message || 'An unexpected error occurred.';
      const details = error.details || (typeof error === 'object' ? JSON.stringify(error) : String(error));
      displayChatMessage('ai', message, true, details);
      finalize();
    }
  }
  
  function updateTopicUI(topic) {
    const convSpan = document.querySelector('.conversation-nav li.active a span');
    if (convSpan) convSpan.textContent = topic;
    const headerSpan = document.getElementById('conversation-title');
    if (headerSpan) headerSpan.textContent = topic;
  }

  // Event Listeners Setup
  if (promptInput) {
    promptInput.addEventListener('input', e => {
      e.target.style.height = 'auto'; // Reset height to shrink if text is deleted
      e.target.style.height = (e.target.scrollHeight) + 'px'; // Set to scroll height
    });
    promptInput.addEventListener('keydown', e => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    });
  }

  if (sendButton) {
    sendButton.onclick = sendMessage; // Initial setup for send action
    sendButton.innerHTML = sendIconHTML; // Set initial icon
    sendButton.title = "Send message";
    // Add class if it's used for default send state styling
    sendButton.classList.add('send-btn-active'); 
  }

  if (toggleSidebar && sidebar) {
    toggleSidebar.addEventListener('click', () => sidebar.classList.toggle('open'));
  }
  
  if (modelSelect && newChatModelInput) {
    modelSelect.addEventListener('change', e => {
        if(newChatModelInput) newChatModelInput.value = e.target.value;
    });
  }
});

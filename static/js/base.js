document.addEventListener('DOMContentLoaded', () => {
    // This listener handles scrolling the chat stream to the bottom
    // whenever a new message is added via HTMX (e.g., from an SSE event).
    const chatStream = document.getElementById('chat-stream');
    if (chatStream) {
        chatStream.addEventListener('htmx:afterSwap', function() {
            chatStream.scrollTop = chatStream.scrollHeight;
        });
    }
});

document.addEventListener('DOMContentLoaded', () => {
    // Automatically attach the CSRF token to all HTMX requests.
    const tokenTag = document.querySelector('meta[name="csrf-token"]');
    const csrfToken = tokenTag ? tokenTag.getAttribute('content') : null;
    if (!csrfToken) {
        return;
    }
    document.body.addEventListener('htmx:configRequest', (event) => {
        event.detail.headers['X-CSRFToken'] = csrfToken;
    });
});

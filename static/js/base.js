document.addEventListener('DOMContentLoaded', () => {
    // This listener handles scrolling the chat stream to the bottom
    // whenever a new message is added via HTMX (e.g., from an SSE event).
    const chatStream = document.getElementById('chat-stream');
    if (chatStream) {
        chatStream.addEventListener('htmx:afterSwap', function() {
            chatStream.scrollTop = chatStream.scrollHeight;

            // Also refresh the Open Questions panel if present
            const qp = document.getElementById('questions-panel');
            if (qp && window.htmx) {
                window.htmx.ajax('GET', '/api/ui/questions/', { target: '#questions-panel', swap: 'innerHTML' });
            }
        });
    }
});
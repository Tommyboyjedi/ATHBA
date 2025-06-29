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
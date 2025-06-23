
  document.body.addEventListener("htmx:afterSwap", function (e) {
    if (e.target.id === "chat-stream") {
      document.body.dispatchEvent(new Event("chat-response"));
    }
  });
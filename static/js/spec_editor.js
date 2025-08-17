let quill = null;

export function initSpecEditor(initialHtml = '') {
  const editor = document.getElementById('editor-container');

  quill = new Quill(editor, {
    theme: 'snow',
    modules: {
      toolbar: [
        ['bold', 'italic', 'underline'],
        [{ list: 'ordered' }, { list: 'bullet' }],
        ['link'],
        [{ header: [1, 2, 3, false] }],
        ['clean']
      ]
    }
  });

  // Load initial content
  quill.clipboard.dangerouslyPasteHTML(initialHtml);

  // Save button logic
  const saveBtn = document.getElementById('save-spec-btn');
  if (saveBtn) {
    saveBtn.addEventListener('click', () => {
      const html = quill.root.innerHTML;
      fetch('/api/ui/spec/', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: html })
      }).then(() => {
        alert('✅ Spec saved!');
      });
    });
  }
}

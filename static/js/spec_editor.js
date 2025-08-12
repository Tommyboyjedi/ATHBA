let quill = null;

function toInitialHtml(data) {
  if (typeof data === 'string') return data;
  if (data && typeof data === 'object') {
    if (Array.isArray(data.sections) && data.sections.length > 0) {
      return data.sections[0]?.body || '';
    }
    if (typeof data.content === 'string') {
      return data.content;
    }
  }
  return '';
}

export function initSpecEditor(initialData = '') {
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

  const initialHtml = toInitialHtml(initialData);
  quill.clipboard.dangerouslyPasteHTML(initialHtml);

  const saveBtn = document.getElementById('save-spec-btn');
  if (saveBtn) {
    saveBtn.addEventListener('click', () => {
      const html = quill.root.innerHTML;
      fetch(window.location.href, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: html })
      }).then(() => {
        alert('✅ Spec saved!');
      });
    });
  }
}

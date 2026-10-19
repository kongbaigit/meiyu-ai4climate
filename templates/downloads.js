document.querySelectorAll('[data-download]').forEach(button => {
  button.addEventListener('click', async () => {
    const status = button.parentElement.querySelector('.download-status');
    button.disabled = true;
    try {
      status.textContent = '正在准备下载…';
      const response = await fetch('downloads.json');
      if (!response.ok) throw new Error('文件清单暂时不可用');
      const entry = (await response.json())[button.dataset.download];
      const parts = [];
      for (let index = 0; index < entry.parts.length; index++) {
        status.textContent = '正在下载 ' + (index + 1) + '/' + entry.parts.length + '，请稍候…';
        const result = await fetch(entry.parts[index]);
        if (!result.ok) throw new Error('下载中断，请重试');
        parts.push(await result.arrayBuffer());
      }
      const blob = new Blob(parts, {type:entry.type});
      if (blob.size !== entry.bytes) throw new Error('文件长度不符，请重试');
      const hash = await crypto.subtle.digest('SHA-256', await blob.arrayBuffer());
      const actual = Array.from(new Uint8Array(hash), x => x.toString(16).padStart(2,'0')).join('');
      if (actual !== entry.sha256) throw new Error('文件校验失败，请重试');
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href=url; link.download=entry.name; document.body.appendChild(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 60000);
      status.textContent = '文件校验通过，已交给浏览器保存。';
    } catch (error) {
      status.textContent = error.message || '下载失败，请稍后重试。';
    } finally { button.disabled=false; }
  });
});

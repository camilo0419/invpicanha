document.querySelectorAll('input[inputmode="decimal"]').forEach(el=>el.addEventListener('input',()=>{el.value=el.value.replace(/[^0-9.,]/g,'')}));

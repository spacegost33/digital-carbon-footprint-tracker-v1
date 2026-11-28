(() => {
    const sidebar = document.getElementById('ctSidebar');
    const toggle = document.getElementById('ctMenuToggle');
    const close = document.getElementById('ctMenuClose');
    const backdrop = document.getElementById('ctMenuBackdrop');
    const main = document.querySelector('main.main');
    if (!sidebar || !toggle || !close || !backdrop || !main) return;
    const mobile = window.matchMedia('(max-width: 900px)');
    const body = document.body;
    let opened = false;
    function setOpen(next, restoreFocus = true) {
        const wasOpen = opened;
        opened = Boolean(next && mobile.matches);
        body.classList.toggle('ct-menu-open', opened);
        toggle.setAttribute('aria-expanded', String(opened));
        backdrop.hidden = !opened;
        main.inert = opened;
        sidebar.inert = mobile.matches && !opened;
        if (opened && !wasOpen) close.focus();
        else if (wasOpen && !opened && restoreFocus && mobile.matches) toggle.focus();
    }
    toggle.addEventListener('click', () => setOpen(!opened));
    close.addEventListener('click', () => setOpen(false));
    backdrop.addEventListener('click', () => setOpen(false));
    document.addEventListener('keydown', event => {
        if (!opened) return;
        if (event.key === 'Escape') { event.preventDefault(); setOpen(false); }
        if (event.key === 'Tab') {
            const items = [...sidebar.querySelectorAll('a[href], button:not([disabled]), summary')]
                .filter(el => el.getClientRects().length && !el.closest('details:not([open]) .ct-nav-children'));
            if (!items.length) return;
            const first = items[0], last = items[items.length - 1];
            if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
            else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
        }
    });
    mobile.addEventListener('change', () => setOpen(false, false));
    // Native details/name gives an accessible accordion in modern browsers.
    // Keep the same single-open behaviour in browsers without name support.
    const groups = [...sidebar.querySelectorAll('.ct-nav-group')];
    groups.forEach(group => group.addEventListener('toggle', () => {
        if (group.open) groups.forEach(other => { if (other !== group) other.open = false; });
    }));
    body.classList.add('ct-nav-ready');
    setOpen(false, false);
})();

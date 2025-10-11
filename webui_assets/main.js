(function() {
    // --- Globals & DOM Elements ---
    const token = new URLSearchParams(location.search).get('token');
    const headers = token ? { 'X-Auth-Token': token } : {};
    let state = { version: 2, menus: {}, buttons: {}, actions: {}, web_apps: {} };
    let isClick = true;

    const menusContainer = document.getElementById('menusContainer');
    const unassignedButtonsContainer = document.getElementById('unassignedButtonsContainer');
    const actionsContainer = document.getElementById('actionsContainer');
    const webappsContainer = document.getElementById('webappsContainer');
    const refreshBtn = document.getElementById('refreshBtn');
    const saveBtn = document.getElementById('saveBtn');
    const addMenuBtn = document.getElementById('addMenuBtn');
    const addUnassignedBtn = document.getElementById('addUnassignedBtn');
    const addActionBtn = document.getElementById('addActionBtn');
    const addWebappBtn = document.getElementById('addWebappBtn');
    const exportBtn = document.getElementById('exportBtn');

    // --- Modal ---
    const modal = document.getElementById('modal');
    const modalTitle = document.getElementById('modalTitle');
    const modalBody = document.getElementById('modalBody');
    const modalFooter = document.getElementById('modalFooter');
    const modalCloseBtn = document.getElementById('modalCloseBtn');
    function openModal(title, bodyEl, footerEl) {
        modalTitle.textContent = title;
        modalBody.innerHTML = '';
        modalBody.appendChild(bodyEl);
        modalFooter.innerHTML = '';
        if (footerEl) modalFooter.appendChild(footerEl);
        modal.classList.add('visible');
    }
    function closeModal() {
        modal.classList.remove('visible');
    }
    modalCloseBtn.onclick = closeModal;
    modal.onclick = (e) => { if (e.target === modal) closeModal(); };

    // --- API & State Management ---
    async function api(path, opts = {}) {
        const options = { headers: { 'Content-Type': 'application/json', ...headers }, ...opts };
        if (options.body && typeof options.body !== 'string') {
            options.body = JSON.stringify(options.body);
        }
        const response = await fetch(path + (token ? (path.includes('?') ? '&' : '?') + 'token=' + encodeURIComponent(token) : ''), options);
        if (!response.ok) {
            const body = await response.text();
            throw new Error(`API Error: ${response.status} ${body}`);
        }
        const contentType = response.headers.get('Content-Type') || '';
        return contentType.includes('application/json') ? response.json() : response.text();
    }
    async function loadState() {
        const data = await api('/api/state');
        state = { version: 2, menus: {}, buttons: {}, actions: {}, web_apps: {}, ...data };
        renderAll();
    }
    function renderAll(opts = {}) {
        const openDetails = new Set();
        if (!opts.openNewId) {
            document.querySelectorAll('#menusContainer details[open]').forEach(details => {
                if(details.dataset.menuId) openDetails.add(details.dataset.menuId);
            });
            document.querySelectorAll('#actionsContainer details[open], #webappsContainer details[open]').forEach(details => {
                if(details.dataset.id) openDetails.add(details.dataset.id);
            });
        }
        
        renderMenus(openDetails);
        renderUnassignedButtons();
        renderActions(openDetails, opts.openNewId && opts.type === 'action' ? opts.openNewId : null);
        renderWebapps(openDetails, opts.openNewId && opts.type === 'webapp' ? opts.openNewId : null);

        if (opts.openNewId) {
            setTimeout(() => {
                const newEl = document.querySelector(`details[data-id="${opts.openNewId}"]`);
                if (newEl) {
                    newEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    newEl.open = true;
                }
            }, 100);
        }
    }

    // --- RENDER FUNCTIONS ---
    function renderMenus(openDetails) {
        menusContainer.innerHTML = '';
        if (!Object.keys(state.menus).length) {
            menusContainer.innerHTML = '<p class="muted">暂无菜单。</p>';
            return;
        }
        Object.keys(state.menus).forEach(menuId => {
            const menu = state.menus[menuId];
            const details = document.createElement('details');
            details.dataset.menuId = menuId;
            const summaryText = `${menuId} (${menu.name || '未命名'})`;
            details.innerHTML = `<summary>${summaryText}</summary>`;
            if (openDetails.has(menuId)) details.open = true;
            
            const content = document.createElement('div');
            content.className = 'details-content';
            const nameField = createField('名称', createInput('text', menu.name || '', val => { menu.name = val; details.querySelector('summary').textContent = `${menuId} (${val || '未命名'})`; }));
            const headerField = createField('标题', createInput('text', menu.header || '', val => { menu.header = val; }));
            const layoutGrid = document.createElement('div');
            layoutGrid.className = 'menu-layout-grid';
            layoutGrid.dataset.menuId = menuId;

            const rows = new Map();
            (menu.items || []).map(id => state.buttons[id]).filter(Boolean).forEach(btn => {
                const rowIndex = btn.layout?.row ?? 0;
                if (!rows.has(rowIndex)) rows.set(rowIndex, []);
                rows.get(rowIndex).push(btn);
            });
            const maxRow = rows.size > 0 ? Math.max(...rows.keys()) : -1;
            for (let i = 0; i <= maxRow; i++) {
                layoutGrid.appendChild(createMenuRow(rows.get(i) || [], menuId, i));
            }
            layoutGrid.appendChild(createMenuRow([], menuId, maxRow + 1));
            
            const deleteBtn = document.createElement('button');
            deleteBtn.className = 'danger';
            deleteBtn.style.marginTop = '16px';
            deleteBtn.textContent = '删除此菜单';
            deleteBtn.onclick = () => {
                if (menuId === 'root') return alert('不能删除 root 根菜单！');
                if (confirm(`确认删除菜单 ${menuId} (${menu.name}) 吗？此菜单中的所有按钮都将变为“未分配”状态。`)) {
                    delete state.menus[menuId];
                    renderAll();
                }
            };
            content.append(nameField, headerField, layoutGrid, deleteBtn);
            details.appendChild(content);
            menusContainer.appendChild(details);
            initSortableForMenu(menuId);
        });
    }

    function renderUnassignedButtons() {
        unassignedButtonsContainer.innerHTML = '';
        const allButtonIds = new Set(Object.keys(state.buttons));
        Object.values(state.menus).forEach(menu => {
            (menu.items || []).forEach(btnId => allButtonIds.delete(btnId));
        });
        
        allButtonIds.forEach(btnId => {
            const button = state.buttons[btnId];
            if (button) unassignedButtonsContainer.appendChild(createMenuButton(button));
        });
        
        initSortableForRow(unassignedButtonsContainer);
    }
    
    function createMenuRow(buttonsInRow, menuId, rowIndex) {
        const rowDiv = document.createElement('div');
        rowDiv.className = 'menu-layout-row';
        rowDiv.dataset.rowIndex = rowIndex;
        rowDiv.dataset.menuId = menuId;
        if (!buttonsInRow || !buttonsInRow.length) {
            rowDiv.classList.add('empty-row');
        } else {
            buttonsInRow.sort((a, b) => (a.layout?.col ?? 0) - (b.layout?.col ?? 0));
            buttonsInRow.forEach(btn => rowDiv.appendChild(createMenuButton(btn)));
        }
        return rowDiv;
    }

    function createMenuButton(btn) {
        const wrapper = document.createElement('div');
        wrapper.className = 'menu-btn-wrapper';
        wrapper.textContent = btn.text || '未命名';
        wrapper.dataset.buttonId = btn.id;
        wrapper.addEventListener('mousedown', () => { isClick = true; });
        wrapper.addEventListener('mousemove', () => { isClick = false; });
        wrapper.addEventListener('mouseup', () => {
            if (isClick) {
                const currentMenuId = wrapper.closest('.menu-layout-grid')?.dataset.menuId || null;
                openButtonEditor(btn.id, currentMenuId);
            }
        });
        return wrapper;
    }

    function initSortableForMenu(menuId) {
        const grid = document.querySelector(`.menu-layout-grid[data-menu-id="${menuId}"]`);
        grid.querySelectorAll('.menu-layout-row').forEach(initSortableForRow);
    }
    
    function updateRowAppearance(row) {
        if (!row) return;
        const hasButtons = row.querySelector('.menu-btn-wrapper') !== null;
        row.classList.toggle('empty-row', !hasButtons);
    }

    function initSortableForRow(rowEl) {
        new Sortable(rowEl, {
            group: 'shared-buttons',
            animation: 150,
            ghostClass: 'sortable-ghost',
            dragClass: 'sortable-drag',
            onEnd: (evt) => {
                updateStateFromDOM();
                
                updateRowAppearance(evt.from);
                updateRowAppearance(evt.to);

                const grid = evt.to.closest('.menu-layout-grid');
                if (grid) {
                    const rows = grid.querySelectorAll('.menu-layout-row');
                    const lastRow = rows[rows.length - 1];
                    if (evt.to === lastRow && lastRow.querySelector('.menu-btn-wrapper')) {
                        const newRow = createMenuRow([], grid.dataset.menuId, rows.length);
                        grid.appendChild(newRow);
                        initSortableForRow(newRow);
                    }
                }
            },
        });
    }

    function updateStateFromDOM() {
        Object.keys(state.menus).forEach(menuId => {
            state.menus[menuId].items = [];
        });

        document.querySelectorAll('.menu-layout-grid').forEach(grid => {
            const menuId = grid.dataset.menuId;
            if (!menuId || !state.menus[menuId]) return;

            const newButtonOrder = [];
            grid.querySelectorAll('.menu-layout-row').forEach((rowEl, rowIndex) => {
                rowEl.querySelectorAll('.menu-btn-wrapper').forEach((btnEl, colIndex) => {
                    const btnId = btnEl.dataset.buttonId;
                    const button = state.buttons[btnId];
                    if (button) {
                        button.layout.row = rowIndex;
                        button.layout.col = colIndex;
                        newButtonOrder.push(btnId);
                    }
                });
            });
            state.menus[menuId].items = newButtonOrder;
        });
    }
    
    function renderActions(openDetails, openNewId) {
        actionsContainer.innerHTML = '';
        if (!Object.keys(state.actions).length) {
            actionsContainer.innerHTML = '<p class="muted">暂无动作。</p>'; return;
        }
        Object.keys(state.actions).forEach(id => {
            const action = state.actions[id];
            const details = document.createElement('details');
            details.dataset.id = id;
            const summaryText = `${id} (${action.name || '未命名'})`;
            details.innerHTML = `<summary>${summaryText}</summary>`;
            if (openDetails.has(id) || id === openNewId) details.open = true;
            const content = createActionWebAppContent('action', id, action);
            details.appendChild(content);
            actionsContainer.appendChild(details);
        });
    }

    function renderWebapps(openDetails, openNewId) {
        webappsContainer.innerHTML = '';
        if (!Object.keys(state.web_apps || {}).length) {
            webappsContainer.innerHTML = '<p class="muted">暂无 WebApp。</p>'; return;
        }
        Object.keys(state.web_apps).forEach(id => {
            const webapp = state.web_apps[id];
            const details = document.createElement('details');
            details.dataset.id = id;
            const summaryText = `${id} (${webapp.name || '未命名'})`;
            details.innerHTML = `<summary>${summaryText}</summary>`;
            if (openDetails.has(id) || id === openNewId) details.open = true;
            const content = createActionWebAppContent('webapp', id, webapp);
            details.appendChild(content);
            webappsContainer.appendChild(details);
        });
    }

    function createActionWebAppContent(type, id, item) {
        const content = document.createElement('div');
        content.className = 'details-content';
        const nameField = createField('名称', createInput('text', item.name || '', val => { item.name = val; document.querySelector(`details[data-id='${id}'] summary`).textContent = `${id} (${val || '未命名'})`; }));
        const descField = createField('描述', createInput('text', item.description || '', val => { item.description = val; }));
        content.append(nameField, descField);

        if (type === 'action') {
            const configInput = createTextarea(JSON.stringify(item.config || {}, null, 2), val => { try { item.config = JSON.parse(val); configInput.style.borderColor = 'var(--border-color)'; } catch { configInput.style.borderColor = 'var(--danger-primary)'; }});
            configInput.dataset.actionId = id;
            content.appendChild(createField('配置 (JSON)', configInput));
        } else {
            const urlField = createField('URL', createInput('text', item.url || '', val => { item.url = val; }));
            content.appendChild(urlField);
        }
        
        const deleteBtn = document.createElement('button');
        deleteBtn.className = 'danger';
        deleteBtn.style.marginTop = '16px';
        deleteBtn.textContent = `删除${type === 'action' ? '动作' : 'WebApp'}`;
        deleteBtn.onclick = () => {
            if (confirm(`确认删除 ${id}?`)) {
                delete state[type === 'action' ? 'actions' : 'web_apps'][id];
                renderAll();
            }
        };
        content.appendChild(deleteBtn);
        return content;
    }

    async function openButtonEditor(buttonId, menuId) {
        const isNew = !buttonId;
        let button = isNew ? 
            { text: '新按钮', type: 'command', payload: {}, layout: { row: 0, col: 0, rowspan: 1, colspan: 1 } } : 
            JSON.parse(JSON.stringify(state.buttons[buttonId]));

        const body = document.createElement('div');
        const textField = createField('显示文本', createInput('text', button.text, v => button.text = v));
        const typeSelect = createSelect(button.type, [ { value: 'command', label: '指令' }, { value: 'url', label: '链接' }, { value: 'submenu', label: '子菜单' }, { value: 'web_app', label: 'WebApp' }, { value: 'action', label: '动作' }], v => { button.type = v; button.payload = {}; renderPayloadFields(); });
        const typeField = createField('类型', typeSelect);
        const payloadContainer = document.createElement('div');

        function renderPayloadFields() {
            payloadContainer.innerHTML = '';
            let payloadField;
            switch (button.type) {
                case 'command': payloadField = createField('指令内容', createInput('text', button.payload.command || '', v => button.payload.command = v)); break;
                case 'url': payloadField = createField('链接URL', createInput('text', button.payload.url || '', v => button.payload.url = v)); break;
                case 'submenu': payloadField = createField('目标菜单', createSelect(button.payload.menu_id || '', getMenuOptions(), v => button.payload.menu_id = v)); break;
                case 'web_app': payloadField = createField('WebApp', createSelect(button.payload.web_app_id || '', Object.keys(state.web_apps || {}).map(id => ({value: id, label: `${state.web_apps[id].name} (${id})`})), v => button.payload.web_app_id = v)); break;
                case 'action': payloadField = createField('动作', createSelect(button.payload.action_id || '', Object.keys(state.actions).map(id => ({value: id, label: `${state.actions[id].name} (${id})`})), v => button.payload.action_id = v)); break;
            }
            if (payloadField) payloadContainer.appendChild(payloadField);
        }
        renderPayloadFields();
        body.append(textField, typeField, payloadContainer);

        const footer = document.createElement('div');
        footer.style.cssText = "width: 100%; display: flex; justify-content: space-between;";
        const leftActions = document.createElement('div'); leftActions.className = 'actions-left';
        const rightActions = document.createElement('div'); rightActions.className = 'actions-right';

        if (!isNew) {
            if (menuId) {
                const removeBtn = document.createElement('button');
                removeBtn.textContent = '从菜单移除'; removeBtn.className = 'danger';
                removeBtn.onclick = () => {
                    if (confirm(`确认要从菜单 "${menuId}" 中移除此按钮吗？`)) {
                        state.menus[menuId].items = state.menus[menuId].items.filter(id => id !== buttonId);
                        closeModal();
                        renderAll();
                    }
                };
                leftActions.append(removeBtn);
            }
            const deleteBtn = document.createElement('button');
            deleteBtn.textContent = '永久删除'; deleteBtn.className = 'danger';
            deleteBtn.style.backgroundColor = 'var(--danger-secondary)';
            deleteBtn.onclick = () => {
                if (confirm(`警告：确认要永久删除按钮 "${button.text}" 吗？`)) {
                    delete state.buttons[buttonId];
                    Object.values(state.menus).forEach(m => { m.items = (m.items || []).filter(id => id !== buttonId); });
                    closeModal();
                    renderAll();
                }
            };
            leftActions.append(deleteBtn);
        }
        const cancelBtn = document.createElement('button');
        cancelBtn.textContent = '取消'; cancelBtn.className = 'secondary';
        cancelBtn.onclick = closeModal;
        const saveBtn = document.createElement('button');
        saveBtn.textContent = isNew ? '创建按钮' : '保存更改';
        saveBtn.onclick = async () => {
            if (isNew) {
                const newId = (await api('/api/util/ids', { method: 'POST', body: { type: 'button' } })).id;
                button.id = newId;
                state.buttons[newId] = button;
            } else {
                state.buttons[buttonId] = button;
            }
            closeModal();
            renderAll();
        };
        rightActions.append(cancelBtn, saveBtn);
        footer.append(leftActions, rightActions);
        openModal(isNew ? '创建新按钮' : `编辑: ${button.text}`, body, footer);
    }
    
    // --- Helpers & Init ---
    function createField(labelText, inputEl) { const field = document.createElement('div'); field.className = 'field'; field.innerHTML = `<label>${labelText}</label>`; field.appendChild(inputEl); return field; }
    function createInput(type, value, onChange) { const input = document.createElement('input'); input.type = type; input.value = value ?? ''; if (onChange) input.oninput = e => onChange(e.target.value); return input; }
    function createSelect(value, options, onChange) { const select = document.createElement('select'); select.innerHTML = `<option value="">（请选择）</option>` + (options || []).map(opt => `<option value="${opt.value}">${opt.label}</option>`).join(''); select.value = value ?? ''; if (onChange) select.onchange = e => onChange(e.target.value); return select; }
    function createTextarea(value, onChange) { const textarea = document.createElement('textarea'); textarea.value = value; if (onChange) textarea.oninput = e => onChange(e.target.value); return textarea; }
    function getMenuOptions(excludeId = null) { return Object.keys(state.menus).filter(id => id !== excludeId).map(id => ({ value: id, label: `${state.menus[id].name} (${id})` })); }
    async function generateId(kind) { return (await api('/api/util/ids', { method: 'POST', body: { type: kind } })).id; }

    // --- Event Listeners ---
    addMenuBtn.onclick = async () => { const id = await generateId('menu'); state.menus[id] = { id, name: '新菜单', header: '新菜单标题', items: [] }; renderAll(); };
    addUnassignedBtn.onclick = () => openButtonEditor(null, null);
    addActionBtn.onclick = async () => { const id = await generateId('action'); state.actions[id] = { id, name: '新动作', kind: 'http', config: { request: { method: 'GET', url: 'https://' } } }; renderAll({ openNewId: id, type: 'action' }); };
    addWebappBtn.onclick = async () => { const id = await generateId('webapp'); state.web_apps = state.web_apps || {}; state.web_apps[id] = { id, name: '新WebApp', kind: 'external', url: 'https://' }; renderAll({ openNewId: id, type: 'webapp' }); };
    refreshBtn.onclick = () => loadState().catch(err => alert(err.message));
    saveBtn.onclick = async () => {
        const actionConfigTextareas = document.querySelectorAll('#actionsContainer textarea[data-action-id]');
        for (const textarea of actionConfigTextareas) {
            try {
                const actionId = textarea.dataset.actionId;
                const config = state.actions[actionId].config;
                if (typeof config !== 'object') {
                   JSON.parse(textarea.value);
                }
            } catch (e) {
                const actionId = textarea.dataset.actionId;
                const actionName = state.actions[actionId]?.name || actionId;
                alert(`保存失败！\n动作 "${actionName}" 的配置 (JSON) 格式错误，请修正后再保存。\n\n${e.message}`);
                const details = textarea.closest('details');
                if (details) details.open = true;
                textarea.focus();
                return;
            }
        }

        try { 
            await api('/api/state', { method: 'PUT', body: state }); 
            alert('保存成功！'); 
        } catch(err) { 
            alert(`保存失败: ${err.message}`); 
        } 
    };
    exportBtn.onclick = () => { const blob = new Blob([JSON.stringify(state, null, 2)], { type: 'application/json' }); const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'tg_button_config.json'; a.click(); URL.revokeObjectURL(a.href); };
    document.querySelector('.tab-nav').addEventListener('click', (e) => { if (e.target.matches('.tab-link')) { const tabId = e.target.dataset.tab; document.querySelectorAll('.tab-link').forEach(link => link.classList.remove('active')); e.target.classList.add('active'); document.querySelectorAll('.tab-content').forEach(content => { content.classList.toggle('active', content.id === tabId); }); } });
    
    // --- Initial Load ---
    loadState().catch(err => console.error('Failed to load initial state:', err));
}());
(function() {
    // --- 全局变量与 DOM 元素 ---
    const token = localStorage.getItem('tg-button-auth-token');

    // --- 身份认证网关 ---
    if (!token) {
        window.location.href = '/login';
        return; // 停止脚本的进一步执行。
    }
    const headers = token ? { 'X-Auth-Token': token } : {};
    let state = { version: 2, menus: {}, buttons: {}, actions: {}, web_apps: {} };
    let modularActions = [];
    let localActions = [];
    let isSecureUploadEnabled = false; // 新增：缓存密码启用状态
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

    // --- 模态框 ---
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

    // --- 全局暴露模态框函数 ---
    window.showInfoModal = showInfoModal;
    window.showConfirmModal = showConfirmModal;
    window.showInputModal = showInputModal;

    function showInfoModal(message, isError = false) {
        const body = document.createElement('p');
        body.innerHTML = message.replace(/\n/g, '<br>');
        if (isError) {
            body.style.color = 'var(--danger-primary)';
        }
        const footer = document.createElement('div');
        footer.style.textAlign = 'right';
        const okBtn = document.createElement('button');
        okBtn.textContent = '确定';
        okBtn.onclick = closeModal;
        footer.appendChild(okBtn);
        openModal(isError ? '错误' : '通知', body, footer);
    }

    function showConfirmModal(title, message, onConfirm, onCancel) {
        const body = document.createElement('p');
        body.innerHTML = message.replace(/\n/g, '<br>');

        const footer = document.createElement('div');
        footer.style.cssText = "width: 100%; display: flex; justify-content: flex-end; gap: 12px;";

        const cancelBtn = document.createElement('button');
        cancelBtn.textContent = '取消';
        cancelBtn.className = 'secondary';
        cancelBtn.onclick = () => {
            closeModal();
            if (onCancel) onCancel();
        };

        const confirmBtn = document.createElement('button');
        confirmBtn.textContent = '确认';
        confirmBtn.className = 'danger';
        confirmBtn.onclick = () => {
            closeModal();
            if (onConfirm) onConfirm();
        };

        footer.append(cancelBtn, confirmBtn);
        openModal(title, body, footer);
    }

    function showInputModal(title, message, inputType = 'text', placeholder = '', onConfirm, onCancel) {
        const body = document.createElement('div');
        const messageEl = document.createElement('p');
        messageEl.innerHTML = message.replace(/\n/g, '<br>');
        body.appendChild(messageEl);

        const input = document.createElement('input');
        input.type = inputType;
        input.placeholder = placeholder;
        input.className = 'modal-input'; // For styling
        input.style.width = 'calc(100% - 20px)'; // Account for padding
        input.style.marginTop = '12px';
        input.autocomplete = 'off';
        body.appendChild(input);

        const footer = document.createElement('div');
        footer.style.cssText = "width: 100%; display: flex; justify-content: flex-end; gap: 12px;";

        const cancelBtn = document.createElement('button');
        cancelBtn.textContent = '取消';
        cancelBtn.className = 'secondary';
        cancelBtn.onclick = () => {
            closeModal();
            if (onCancel) onCancel();
        };

        const confirmBtn = document.createElement('button');
        confirmBtn.textContent = '确认';
        confirmBtn.onclick = () => {
            const value = input.value;
            closeModal();
            if (onConfirm) onConfirm(value);
        };

        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                confirmBtn.click();
            } else if (e.key === 'Escape') {
                cancelBtn.click();
            }
        });

        footer.append(cancelBtn, confirmBtn);
        openModal(title, body, footer);

        setTimeout(() => input.focus(), 50);
    }

    // --- API 和状态管理 ---
    async function api(path, opts = {}) {
        const options = { headers: { 'Content-Type': 'application/json', ...headers }, ...opts };
        if (options.body && typeof options.body !== 'string') {
            options.body = JSON.stringify(options.body);
        }
        const response = await fetch(path, options);
        if (!response.ok) {
            if (response.status === 401) {
                // 未授权，可能是令牌过期或无效
                localStorage.removeItem('tg-button-auth-token');
                window.location.href = '/login';
                throw new Error('认证失败，请重新登录。');
            }
            const body = await response.text();
            throw new Error(`API Error: ${response.status} ${body}`);
        }
        const contentType = response.headers.get('Content-Type') || '';
        return contentType.includes('application/json') ? response.json() : response.text();
    }
    async function loadState() {
        const [stateData, modularActionsData, localActionsData] = await Promise.all([
            api('/api/state'),
            api('/api/actions/modular/available').catch(err => {
                console.error("获取模块化动作失败:", err);
                showInfoModal("加载模块化动作列表失败，部分功能可能无法使用。", true);
                return { actions: [], secure_upload_enabled: false }; // 确保在失败时有默认值
            }),
            api('/api/actions/local/available').catch(err => {
                console.error("获取本地动作失败:", err);
                showInfoModal("加载本地动作列表失败，部分功能可能无法使用。", true);
                return { actions: [] };
            })
        ]);

        state = { version: 2, menus: {}, buttons: {}, actions: {}, web_apps: {}, ...stateData };
        modularActions = modularActionsData.actions || [];
        isSecureUploadEnabled = modularActionsData.secure_upload_enabled || false; // 保存从后端获取的状态
        localActions = localActionsData.actions || [];
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

                // 同时刷新工作流编辑器，确保其始终同步。
        if (window.tgButtonEditor) {
            const allActions = {};

            // 1. 内置动作 (来自 state)
            for (const actionId in state.actions) {
                allActions[actionId] = {
                    ...state.actions[actionId], // 复制原始属性
                    id: actionId, // 确保 id 属性存在
                    name: state.actions[actionId].name || actionId,
                    description: state.actions[actionId].description || ''
                };
            }

            // 2. 本地动作
            (localActions || []).forEach(localAction => {
                const actionId = localAction.name; // ID 即为其名称
                allActions[actionId] = {
                    name: `[本地] ${localAction.name}`,
                    description: localAction.description,
                    parameters: localAction.parameters,
                    id: actionId, // 添加关键的 id 属性
                    isLocal: true
                };
            });

            // 3. 模块化动作
            (modularActions || []).forEach(modAction => {
                allActions[modAction.id] = {
                    name: `${modAction.name}`,
                    description: modAction.description,
                    inputs: modAction.inputs,
                    outputs: modAction.outputs,
                    id: modAction.id, // 这里 id 本就是正确的
                    isModular: true
                };
            });

            window.tgButtonEditor.refreshPalette(allActions, isSecureUploadEnabled);
            window.tgButtonEditor.refreshWorkflows();
        }

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

    // --- 渲染函数 ---
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
            const headerField = createField('标题', createTextarea(menu.header || '', val => { menu.header = val; }));
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
                if (menuId === 'root') return showInfoModal('不能删除 root 根菜单！', true);
                showConfirmModal('确认删除菜单', `您确定要删除菜单 “${menu.name}” 吗？<br><br>此菜单中的所有按钮都将变为“未分配”状态。`, () => {
                    delete state.menus[menuId];
                    renderAll();
                });
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
                // --- 新的、状态驱动的逻辑 ---
                const buttonId = evt.item.dataset.buttonId;
                if (!buttonId || !state.buttons[buttonId]) return;

                const fromMenuId = evt.from.closest('.menu-layout-grid')?.dataset.menuId;
                const toMenuId = evt.to.closest('.menu-layout-grid')?.dataset.menuId;

                // 核心逻辑: 拖拽结束后，根据 DOM 的最终状态，一次性地、精确地更新 state

                // 1. 如果按钮从一个菜单中拖出，先从旧菜单的 state.items 中移除
                if (fromMenuId && fromMenuId !== toMenuId) {
                    if (state.menus[fromMenuId]) {
                        state.menus[fromMenuId].items = state.menus[fromMenuId].items.filter(id => id !== buttonId);
                    }
                }

                // 2. 如果按钮被拖入一个菜单，更新该菜单的整个 state
                if (toMenuId) {
                    const grid = evt.to.closest('.menu-layout-grid');
                    const newButtonOrder = [];
                    grid.querySelectorAll('.menu-layout-row').forEach((rowEl, rowIndex) => {
                        rowEl.querySelectorAll('.menu-btn-wrapper').forEach((btnEl, colIndex) => {
                            const btnId = btnEl.dataset.buttonId;
                            if (btnId && state.buttons[btnId]) {
                                state.buttons[btnId].layout.row = rowIndex;
                                state.buttons[btnId].layout.col = colIndex;
                                newButtonOrder.push(btnId);
                            }
                        });
                    });
                    state.menus[toMenuId].items = newButtonOrder;
                } else {
                    // 如果拖入“未分配”区域，清理其布局信息
                    const button = state.buttons[buttonId];
                    if(button) {
                        delete button.layout.row;
                        delete button.layout.col;
                    }
                }

                // 3. 视觉更新和辅助逻辑
                updateRowAppearance(evt.from);
                updateRowAppearance(evt.to);

                const toGrid = evt.to.closest('.menu-layout-grid');
                if (toGrid) {
                    const rows = toGrid.querySelectorAll('.menu-layout-row');
                    const lastRow = rows[rows.length - 1];
                    if (evt.to === lastRow && lastRow.querySelector('.menu-btn-wrapper')) {
                        const newRow = createMenuRow([], toGrid.dataset.menuId, rows.length);
                        toGrid.appendChild(newRow);
                        initSortableForRow(newRow);
                    }
                }

                // 如果拖拽涉及“未分配”区域，需要重新渲染该区域以保证同步
                if (!fromMenuId || !toMenuId) {
                    renderUnassignedButtons();
                }
            },
        });
    }


    /**
     * @description 通用的列表项渲染函数，用于渲染 Actions 和 WebApps 列表，减少代码重复。
     * @param {HTMLElement} container - 渲染内容的父容器。
     * @param {object} items - 要渲染的数据对象 (e.g., state.actions)。
     * @param {string} type - 渲染的类型 ('action' or 'webapp')。
     * @param {string} singularName - 类型的单数中文名 (e.g., '动作')。
     * @param {Set<string>} openDetails - 需要默认展开的项的 ID 集合。
     * @param {string|null} openNewId - 如果有新创建的项，其 ID。
     */
    function renderDetailsList(container, items, type, singularName, openDetails, openNewId) {
        container.innerHTML = '';
        if (!items || !Object.keys(items).length) {
            container.innerHTML = `<p class="muted">暂无${singularName}。</p>`;
            return;
        }
        const sortedKeys = Object.keys(items).sort((a, b) => (items[a].name || a).localeCompare(items[b].name || b));
        sortedKeys.forEach(id => {
            const item = items[id];
            const details = document.createElement('details');
            details.dataset.id = id;
            const summaryText = `${id} (${item.name || '未命名'})`;
            details.innerHTML = `<summary>${summaryText}</summary>`;
            if (openDetails.has(id) || id === openNewId) details.open = true;
            const content = createActionWebAppContent(type, id, item);
            details.appendChild(content);
            container.appendChild(details);
        });
    }

    function renderActions(openDetails, openNewId) {
        renderDetailsList(actionsContainer, state.actions, 'action', '动作', openDetails, openNewId);
    }

    function renderWebapps(openDetails, openNewId) {
        renderDetailsList(webappsContainer, state.web_apps, 'webapp', 'WebApp', openDetails, openNewId);
    }

    function createActionWebAppContent(type, id, item) {
        const content = document.createElement('div');
        content.className = 'details-content';
        const nameField = createField('名称', createInput('text', item.name || '', val => { item.name = val; document.querySelector(`details[data-id='${id}'] summary`).textContent = `${id} (${val || '未命名'})`; }));
        const descField = createField('描述', createTextarea(item.description || '', val => { item.description = val; }));
        content.append(nameField, descField);

        if (type === 'action') {
            const configContainer = document.createElement('div');

            const renderActionConfig = (container) => {
                container.innerHTML = ''; // 清空旧的配置
                const currentKind = item.kind || 'http';

                // http 或 local 类型
                const configInput = createTextarea(JSON.stringify(item.config || {}, null, 2), val => {
                    try {
                        item.config = JSON.parse(val);
                        configInput.style.borderColor = 'var(--border-color)';
                    } catch {
                        configInput.style.borderColor = 'var(--danger-primary)';
                    }
                });
                configInput.classList.add('json-config-input');
                container.appendChild(createField('配置 (JSON)', configInput));
            };

            const kindSelect = createSelect(item.kind || 'http',
                [
                    { value: 'http', label: 'HTTP 请求' },
                    { value: 'local', label: '本地动作' }
                ],
                val => {
                    item.kind = val;
                    item.config = {};
                    renderActionConfig(configContainer);
                }
            );
            content.appendChild(createField('动作类型', kindSelect));
            content.appendChild(configContainer);

            renderActionConfig(configContainer); // 初始渲染

        } else { // webapp 类型处理
            const urlField = createField('URL', createInput('text', item.url || '', val => { item.url = val; }));
            content.appendChild(urlField);
        }

        const deleteBtn = document.createElement('button');
        deleteBtn.className = 'danger';
        deleteBtn.style.marginTop = '16px';
        deleteBtn.textContent = `删除${type === 'action' ? '动作' : 'WebApp'}`;
        deleteBtn.onclick = () => {
            showConfirmModal(`确认删除`, `您确定要删除 ${type === 'action' ? '动作' : 'WebApp'} “${item.name || id}” 吗？`, () => {
                delete state[type === 'action' ? 'actions' : 'web_apps'][id];
                renderAll();
            });
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
        const typeSelect = createSelect(button.type, [ { value: 'command', label: '指令' }, { value: 'url', label: '链接' }, { value: 'submenu', label: '子菜单' }, { value: 'web_app', label: 'WebApp' }, { value: 'action', label: '动作' }, { value: 'workflow', label: '工作流' }, { value: 'inline_query', label: '插入文本' }, { value: 'switch_inline_query', label: '转发查询' }, { value: 'raw', label: '原始回调' } ], v => { button.type = v; button.payload = {}; renderPayloadFields(); });
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
                case 'action':
                    const actionOptions = Object.keys(state.actions || {}).map(id => ({ value: id, label: `${state.actions[id].name} (${id})` }));
                    payloadField = createField('动作', createSelect(button.payload.action_id || '', actionOptions, v => button.payload.action_id = v));
                    break;
                case 'workflow':
                    const wfOptions = Object.keys(state.workflows || {}).map(id => ({ value: id, label: state.workflows[id].name || id }));
                    payloadField = createField('工作流', createSelect(button.payload.workflow_id || '', wfOptions, v => button.payload.workflow_id = v));
                    break;
                case 'inline_query': payloadField = createField('插入内容', createInput('text', button.payload.query || '', v => button.payload.query = v)); break;
                case 'raw': payloadField = createField('回调数据', createTextarea(button.payload.callback_data || '', v => button.payload.callback_data = v)); break;
                case 'switch_inline_query': payloadField = createField('查询内容', createInput('text', button.payload.query || '', v => button.payload.query = v)); break;
            }
            if (payloadField) payloadContainer.appendChild(payloadField);

            const testBtn = modalFooter.querySelector('.test-action-btn');
            if (testBtn) {
                testBtn.style.display = button.type === 'action' ? '' : 'none';
            }
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
                    showConfirmModal('确认移除', `您确定要从菜单 “${menuId}” 中移除此按钮吗？`, () => {
                        state.menus[menuId].items = state.menus[menuId].items.filter(id => id !== buttonId);
                        closeModal();
                        renderAll();
                    });
                };
                leftActions.append(removeBtn);
            }
            const deleteBtn = document.createElement('button');
            deleteBtn.textContent = '永久删除'; deleteBtn.className = 'danger';
            deleteBtn.style.backgroundColor = 'var(--danger-secondary)';
            deleteBtn.onclick = () => {
                showConfirmModal('确认永久删除', `警告：您确定要永久删除按钮 “${button.text}” 吗？<br><br>此操作不可撤销。`, () => {
                    delete state.buttons[buttonId];
                    Object.values(state.menus).forEach(m => { m.items = (m.items || []).filter(id => id !== buttonId); });
                    closeModal();
                    renderAll();
                });
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
        const testBtn = document.createElement('button');
        testBtn.textContent = '测试动作';
        testBtn.className = 'secondary test-action-btn';

        // 错误修复：在模态框打开时，根据按钮类型设置初始可见性。
        testBtn.style.display = button.type === 'action' ? '' : 'none';

        testBtn.onclick = async () => {
            const actionId = button.payload.action_id;
            const action = state.actions[actionId];
            if (!action) {
                showInfoModal(`错误：在当前状态中未找到 ID 为 “${actionId}” 的动作。请先保存或检查动作是否存在。`, true);
                return;
            }
            try {
                const result = await api('/api/actions/test', {
                    method: 'POST',
                    body: { button, menu_id: menuId, action_id: actionId, action: action }
                });
                renderTestResultModal(result);
            } catch (err) {
                renderTestResultModal({ success: false, error: err.message });
            }
        };

        rightActions.append(cancelBtn, testBtn, saveBtn);
        footer.append(leftActions, rightActions);
        openModal(isNew ? '创建新按钮' : `编辑: ${button.text}`, body, footer);
    }
    
    function renderTestResultModal(result) {
        const body = document.createElement('div');
        body.className = 'test-result-display';

        const summary = document.createElement('div');
        summary.className = 'test-result-summary';
        summary.style.marginBottom = '16px';

        const fields = {
            'success': { label: '执行成功', format: v => v ? '✅ 是' : '❌ 否' },
            'error': { label: '错误信息' },
            'new_text': { label: '返回的新文本' },
            'next_menu_id': { label: '跳转的菜单ID' },
            'should_edit_message': { label: '是否需要编辑消息', format: v => v ? '是' : '否' },
        };

        let hasContent = false;
        for (const key in fields) {
            if (Object.prototype.hasOwnProperty.call(result, key) && result[key] !== null && result[key] !== '') {
                const fieldDiv = document.createElement('div');
                fieldDiv.style.marginBottom = '8px';
                const value = fields[key].format ? fields[key].format(result[key]) : result[key];

                const labelStrong = document.createElement('strong');
                labelStrong.textContent = `${fields[key].label}: `;

                const valueSpan = document.createElement('span');
                valueSpan.textContent = value;

                if (key === 'error') {
                    valueSpan.style.color = 'var(--danger-primary)';
                }

                if (key === 'new_text') {
                    valueSpan.style.whiteSpace = 'pre-wrap';
                    valueSpan.style.wordBreak = 'break-word';
                    valueSpan.style.display = 'block';
                    valueSpan.style.marginTop = '4px';
                    valueSpan.style.padding = '8px';
                    valueSpan.style.borderRadius = '4px';
                    valueSpan.style.backgroundColor = 'var(--background-secondary)';
                }

                fieldDiv.appendChild(labelStrong);
                fieldDiv.appendChild(valueSpan);
                summary.appendChild(fieldDiv);
                hasContent = true;
            }
        }
        if (!hasContent) {
            summary.innerHTML = '<p class="muted">没有可供显示的摘要信息。</p>';
        }

        body.appendChild(summary);

        const rawDetails = document.createElement('details');
        rawDetails.innerHTML = '<summary style="cursor: pointer;">查看原始 JSON 响应</summary>';
        const rawPre = document.createElement('pre');
        rawPre.style.cssText = 'background-color: var(--background-secondary); padding: 8px; border-radius: 4px;';
        rawPre.textContent = JSON.stringify(result, null, 2);
        rawDetails.appendChild(rawPre);
        body.appendChild(rawDetails);

        const footer = document.createElement('div');
        const okBtn = document.createElement('button');
        okBtn.textContent = '关闭';
        okBtn.onclick = closeModal;
        footer.appendChild(okBtn);

        openModal('动作测试结果', body, footer);
    }

    function openNodeConfigModal(node) {
        if (!node || !node.data || !node.data.action) {
            console.warn("无法配置节点: 动作数据丢失。", node);
            showInfoModal("无法配置此节点，因为它缺少内部动作定义。", true);
            return;
        }

        const action = node.data.action;
        const rawNodeData = node.data.data ? { ...node.data.data } : {};
        const conditionConfig = Object.prototype.hasOwnProperty.call(
            rawNodeData,
            "__condition__"
        )
            ? rawNodeData.__condition__
            : undefined;
        if (Object.prototype.hasOwnProperty.call(rawNodeData, "__condition__")) {
            delete rawNodeData.__condition__;
        }
        const currentData = rawNodeData;
        const title = `配置节点: ${action.name || action.id}`;

        const body = document.createElement('div');
        body.className = 'node-config-form';

        const conditionSectionHeader = document.createElement('h4');
        conditionSectionHeader.textContent = '执行条件';
        conditionSectionHeader.style.marginTop = '0';
        body.appendChild(conditionSectionHeader);

        const conditionIntro = document.createElement('p');
        conditionIntro.className = 'field-description muted';
        conditionIntro.style.margin = '0 0 12px 0';
        conditionIntro.textContent = '可以在这里设置该节点的触发条件；当条件不成立时，节点以及所有下游节点都会被跳过。除了手动填写模板，还可以直接选择上游连线提供的布尔值。';
        body.appendChild(conditionIntro);

        const actionInputs = action.isModular
            ? (action.inputs || [])
            : (action.isLocal ? (action.parameters || []) : []);
        const actionOutputs = action.isModular ? (action.outputs || []) : [];

        const buildButtonOptions = () => {
            const buttons = state.buttons || {};
            const menus = state.menus || {};
            const buttonToMenu = {};

            Object.values(menus).forEach(menu => {
                if (!menu || !Array.isArray(menu.items)) return;
                menu.items.forEach(btnId => {
                    if (btnId && !buttonToMenu[btnId]) {
                        const name = menu.name || menu.id || '';
                        buttonToMenu[btnId] = name
                            ? `${name} (${menu.id})`
                            : `${menu.id || '未命名菜单'}`;
                    }
                });
            });

            return Object.keys(buttons).map(id => {
                const btn = buttons[id] || {};
                const textLabel = btn.text || '(未命名按钮)';
                const menuLabel = buttonToMenu[id] || '未分配菜单';
                return {
                    value: id,
                    label: `${textLabel} · ${menuLabel} · ${id}`,
                };
            }).sort((a, b) => a.label.localeCompare(b.label));
        };

        const cachedButtonOptions = buildButtonOptions();

        const collectConditionLinks = () => {
            if (!window.tgButtonEditor || typeof window.tgButtonEditor.getNodeById !== 'function') {
                return [];
            }

            const links = [];
            (actionInputs || []).forEach((param, index) => {
                const portName = `input_${index + 1}`;
                const port = node.inputs[portName];
                const connections = (port && Array.isArray(port.connections)) ? port.connections : [];

                connections.forEach(conn => {
                    const upstreamNode = window.tgButtonEditor.getNodeById(conn.node);
                    const upstreamAction = upstreamNode && upstreamNode.data ? upstreamNode.data.action : null;
                    if (!upstreamAction) return;

                    const outputIndex = parseInt(String(conn.output).replace('output_', ''), 10) - 1;
                    if (Number.isNaN(outputIndex)) return;

                    const upstreamOutputs = upstreamAction.outputs || [];
                    const upstreamOutput = upstreamOutputs[outputIndex] || {};
                    const upstreamOutputName = upstreamOutput.name || conn.output || `output_${outputIndex + 1}`;

                    links.push({
                        paramName: param.name,
                        paramLabel: `${param.name}${param.type ? ` (${param.type})` : ''}`,
                        paramType: param.type || '',
                        upstreamNodeId: conn.node,
                        upstreamNodeName: upstreamAction.name || upstreamAction.id || conn.node,
                        upstreamActionId: upstreamAction.id,
                        upstreamOutputName,
                        upstreamOutputLabel: upstreamOutput.description || upstreamOutputName,
                        upstreamOutputType: upstreamOutput.type || '',
                        expression: `{{ inputs.${param.name} }}`,
                    });
                });
            });

            return links;
        };

        const conditionLinks = collectConditionLinks();
        const branchConditionLinks = conditionLinks.filter(link => link.upstreamActionId === 'branch_condition');
        const booleanConditionLinks = conditionLinks.filter(link => {
            const outputType = (link.upstreamOutputType || '').toLowerCase();
            const paramType = (link.paramType || '').toLowerCase();
            return (
                link.upstreamActionId === 'branch_condition'
                || outputType === 'boolean'
                || outputType === 'bool'
                || paramType === 'boolean'
            );
        });

        let linkedConditionTarget = '';
        let linkedConditionNegate = false;
        const preferredConditionLink = branchConditionLinks.find(link => link.upstreamOutputName === 'result')
            || branchConditionLinks[0]
            || booleanConditionLinks[0]
            || null;

        const detectConditionMode = (value) => {
            if (value === undefined || value === null) return 'none';
            if (typeof value === 'boolean') return 'boolean';
            if (typeof value === 'string') return 'template';
            if (value && typeof value === 'object') {
                const typeHint = String(value.type || value.kind || '').toLowerCase();
                if (typeHint === 'input' || typeHint === 'port' || typeHint === 'input_ref') {
                    return 'linked';
                }
            }
            return 'json';
        };

        let conditionMode = detectConditionMode(conditionConfig);
        let conditionBoolValue = typeof conditionConfig === 'boolean' ? conditionConfig : true;
        let conditionTemplateValue = typeof conditionConfig === 'string' ? conditionConfig : '';
        let conditionJsonValue = conditionMode === 'json'
            ? (() => {
                try {
                    return JSON.stringify(conditionConfig, null, 2);
                } catch (err) {
                    console.warn('无法格式化条件配置，将使用原始值。', err);
                    return String(conditionConfig ?? '');
                }
            })()
            : '';

        if (conditionMode === 'linked' && booleanConditionLinks.length === 0) {
            conditionMode = 'template';
        }
        if (conditionMode === 'linked' && conditionConfig && typeof conditionConfig === 'object') {
            linkedConditionTarget = String(conditionConfig.name ?? conditionConfig.input ?? conditionConfig.field ?? '');
            linkedConditionNegate = Boolean(conditionConfig.negate);
        }

        const conditionModeSelect = document.createElement('select');
        const conditionModeOptions = [
            { value: 'none', label: '不设置条件（始终执行）' },
            { value: 'boolean', label: '简单布尔值' },
        ];
        if (booleanConditionLinks.length > 0) {
            conditionModeOptions.push({ value: 'linked', label: '来自上游连线' });
        }
        conditionModeOptions.push(
            { value: 'template', label: '模板表达式（Jinja2）' },
            { value: 'json', label: '高级 JSON 配置' },
        );
        conditionModeOptions.forEach(opt => {
            const optionEl = document.createElement('option');
            optionEl.value = opt.value;
            optionEl.textContent = opt.label;
            conditionModeSelect.appendChild(optionEl);
        });
        if (!conditionModeOptions.some(opt => opt.value === conditionMode)) {
            conditionMode = 'template';
        }
        conditionModeSelect.value = conditionMode;

        const conditionModeField = createField('条件类型', conditionModeSelect);
        body.appendChild(conditionModeField);

        const conditionDetailsWrapper = document.createElement('div');
        const conditionDetailsField = createField('条件配置', conditionDetailsWrapper);
        body.appendChild(conditionDetailsField);

        const renderConditionFields = () => {
            conditionDetailsWrapper.innerHTML = '';
            if (conditionMode === 'none') {
                const tip = document.createElement('p');
                tip.className = 'field-description muted';
                tip.style.margin = '4px 0 0 0';
                tip.textContent = '未设置条件时，节点总是会执行。';
                conditionDetailsWrapper.appendChild(tip);
                return;
            }

            if (conditionMode === 'boolean') {
                const select = document.createElement('select');
                [
                    { value: 'true', label: 'True（执行）' },
                    { value: 'false', label: 'False（跳过）' },
                ].forEach(opt => {
                    const optionEl = document.createElement('option');
                    optionEl.value = opt.value;
                    optionEl.textContent = opt.label;
                    select.appendChild(optionEl);
                });
                select.value = conditionBoolValue ? 'true' : 'false';
                select.onchange = (e) => {
                    conditionBoolValue = e.target.value === 'true';
                };

                const hint = document.createElement('p');
                hint.className = 'field-description muted';
                hint.style.margin = '8px 0 0 0';
                hint.textContent = '选择 False 可以强制跳过该节点（常用于调试）。';

                conditionDetailsWrapper.appendChild(select);
                conditionDetailsWrapper.appendChild(hint);
                return;
            }

            if (conditionMode === 'linked') {
                if (booleanConditionLinks.length === 0) {
                    const tip = document.createElement('p');
                    tip.className = 'field-description muted';
                    tip.style.margin = '4px 0 0 0';
                    tip.textContent = '未检测到可用的布尔连线，请先将上游节点的布尔输出连接到当前节点的任一输入端口。';
                    conditionDetailsWrapper.appendChild(tip);
                    return;
                }

                if (!linkedConditionTarget) {
                    const defaultLink = (preferredConditionLink && booleanConditionLinks.find(link => link.paramName === preferredConditionLink.paramName))
                        || booleanConditionLinks[0];
                    linkedConditionTarget = defaultLink ? defaultLink.paramName : '';
                }

                const list = document.createElement('div');
                list.className = 'linked-condition-list';
                list.style.display = 'flex';
                list.style.flexDirection = 'column';
                list.style.gap = '8px';

                booleanConditionLinks.forEach(link => {
                    const option = document.createElement('label');
                    option.className = 'linked-condition-option';
                    option.style.display = 'flex';
                    option.style.flexDirection = 'column';
                    option.style.gap = '4px';
                    option.style.padding = '8px';
                    option.style.border = '1px solid var(--border-color)';
                    option.style.borderRadius = '6px';

                    const row = document.createElement('div');
                    row.style.display = 'flex';
                    row.style.alignItems = 'center';
                    row.style.gap = '8px';

                    const radio = document.createElement('input');
                    radio.type = 'radio';
                    radio.name = 'linked-condition-target';
                    radio.value = link.paramName;
                    radio.checked = linkedConditionTarget === link.paramName;
                    radio.onchange = () => {
                        linkedConditionTarget = link.paramName;
                    };

                    const info = document.createElement('div');
                    info.style.flex = '1';
                    info.innerHTML = `<strong>${link.upstreamNodeName}</strong> · ${link.upstreamOutputLabel}`;

                    const copyBtn = document.createElement('button');
                    copyBtn.type = 'button';
                    copyBtn.className = 'secondary';
                    copyBtn.textContent = '复制模板';
                    copyBtn.onclick = async () => {
                        try {
                            await navigator.clipboard.writeText(link.expression);
                            showInfoModal('已复制模板表达式。');
                        } catch (err) {
                            console.warn('复制模板失败', err);
                            showInfoModal('复制失败，请手动选择后复制。', true);
                        }
                    };

                    row.append(radio, info, copyBtn);

                    const hint = document.createElement('div');
                    hint.className = 'field-description muted';
                    hint.innerHTML = `对应输入：<code>${link.paramLabel}</code><br>模板：<code>${link.expression}</code>`;

                    option.append(row, hint);
                    list.appendChild(option);
                });

                conditionDetailsWrapper.appendChild(list);

                const negateWrapper = document.createElement('label');
                negateWrapper.style.display = 'flex';
                negateWrapper.style.alignItems = 'center';
                negateWrapper.style.gap = '8px';
                negateWrapper.style.marginTop = '8px';

                const negateCheckbox = document.createElement('input');
                negateCheckbox.type = 'checkbox';
                negateCheckbox.checked = linkedConditionNegate;
                negateCheckbox.onchange = (e) => {
                    linkedConditionNegate = e.target.checked;
                };

                negateWrapper.append(negateCheckbox, document.createTextNode('取反条件（布尔值为 False 时执行节点）'));
                conditionDetailsWrapper.appendChild(negateWrapper);

                const tip = document.createElement('p');
                tip.className = 'field-description muted';
                tip.style.margin = '6px 0 0 0';
                tip.textContent = '保存后将直接读取所选输入端口的布尔值，避免手动维护模板表达式。';
                conditionDetailsWrapper.appendChild(tip);
                return;
            }

            if (conditionMode === 'template') {
                if (!conditionTemplateValue.trim() && preferredConditionLink) {
                    conditionTemplateValue = preferredConditionLink.expression;
                }
                const textarea = createTextarea(conditionTemplateValue, (val) => {
                    conditionTemplateValue = val;
                });
                textarea.placeholder = '例如：{{ inputs.branch_result }} 或 {{ variables.my_flag }}';
                textarea.rows = 3;

                const hint = document.createElement('p');
                hint.className = 'field-description muted';
                hint.style.margin = '8px 0 0 0';
                hint.textContent = '模板渲染结果会被解释为布尔值：空字符串、0、false 会视为条件不满足。';

                const usage = document.createElement('p');
                usage.className = 'field-description muted';
                usage.style.margin = '4px 0 0 0';
                const connectedInputs = [];
                (actionInputs || []).forEach((param, index) => {
                    const portName = `input_${index + 1}`;
                    if (node.inputs[portName] && node.inputs[portName].connections.length > 0) {
                        connectedInputs.push(param.name);
                    }
                });
                if (connectedInputs.length > 0) {
                    usage.textContent = `已连接的输入：${connectedInputs.join('、')}。可通过 {{ inputs.参数名 }} 读取对应值，或使用 {{ variables.别名 }} 访问全局变量。也可以切换到“来自上游连线”条件类型直接复用这些布尔值。`;
                } else if ((actionInputs || []).length > 0) {
                    const names = actionInputs.map(param => param.name).join('、 ');
                    usage.textContent = `当前动作支持的输入包含：${names}。当某个输入连接了上游节点后，可在模板中写 {{ inputs.参数名 }} 读取，或直接在条件类型中选择“来自上游连线”。`;
                } else {
                    usage.textContent = '如果只依赖全局变量，可以直接写 {{ variables.变量名 }}；若需要来自上游的布尔值，可先连线后使用“来自上游连线”条件类型完成配置。';
                }

                conditionDetailsWrapper.appendChild(textarea);
                conditionDetailsWrapper.appendChild(hint);
                conditionDetailsWrapper.appendChild(usage);

                if (booleanConditionLinks.length > 0) {
                    const branchHint = document.createElement('p');
                    branchHint.className = 'field-description muted';
                    branchHint.style.margin = '4px 0 0 0';
                    branchHint.innerHTML = '检测到可用的布尔来源：'
                        + booleanConditionLinks.map(link => `<span><code>${link.expression}</code> — ${link.upstreamNodeName} · ${link.upstreamOutputLabel}</span>`).join('、');
                    conditionDetailsWrapper.appendChild(branchHint);

                    const quickFillWrapper = document.createElement('div');
                    quickFillWrapper.style.margin = '6px 0 0 0';
                    quickFillWrapper.style.display = 'flex';
                    quickFillWrapper.style.flexWrap = 'wrap';
                    quickFillWrapper.style.gap = '6px';

                    booleanConditionLinks.forEach(link => {
                        const btn = document.createElement('button');
                        btn.type = 'button';
                        btn.className = 'secondary';
                        btn.textContent = `${link.upstreamNodeName} → ${link.upstreamOutputName}`;
                        btn.title = link.expression;
                        btn.onclick = () => {
                            conditionTemplateValue = link.expression;
                            textarea.value = link.expression;
                            textarea.focus();
                        };
                        quickFillWrapper.appendChild(btn);
                    });

                    conditionDetailsWrapper.appendChild(quickFillWrapper);
                }
                return;
            }

            const textarea = createTextarea(conditionJsonValue, (val) => {
                conditionJsonValue = val;
                try {
                    if (val.trim()) {
                        JSON.parse(val);
                        textarea.style.borderColor = 'var(--border-color)';
                    } else {
                        textarea.style.borderColor = 'var(--border-color)';
                    }
                } catch (err) {
                    textarea.style.borderColor = 'var(--danger-primary)';
                }
            });
            textarea.classList.add('json-config-input');
            textarea.placeholder = '{"type": "template", "template": "{{ inputs.ok }}" }';

            const hint = document.createElement('p');
            hint.className = 'field-description muted';
            hint.style.margin = '8px 0 0 0';
            hint.textContent = '适用于需要复杂条件的情况；填写任意合法的 JSON，保存前会尝试解析。';

            const usage = document.createElement('p');
            usage.className = 'field-description muted';
            usage.style.margin = '4px 0 0 0';
            usage.textContent = '模板型配置里同样支持 {{ inputs.参数名 }} 与 {{ variables.变量名 }}。通过“条件判断”模块可以快速生成这些布尔变量。';

            conditionDetailsWrapper.appendChild(textarea);
            conditionDetailsWrapper.appendChild(hint);
            conditionDetailsWrapper.appendChild(usage);
        };

        conditionModeSelect.onchange = (e) => {
            conditionMode = e.target.value;
            renderConditionFields();
        };

        renderConditionFields();

        if ((!actionInputs || actionInputs.length === 0) && (!actionOutputs || actionOutputs.length === 0)) {
            const noParams = document.createElement('p');
            noParams.className = 'muted';
            noParams.style.marginTop = '16px';
            noParams.textContent = '此节点没有可配置或可查看的参数。';
            body.appendChild(noParams);
        } else {
            if (actionInputs && actionInputs.length > 0) {
                const inputsHeader = document.createElement('h4');
                inputsHeader.textContent = '输入参数';
                inputsHeader.style.marginTop = '0';
                body.appendChild(inputsHeader);

                actionInputs.forEach((param, index) => {
                    const paramName = param.name;
                    const paramLabel = `${param.name}${param.type ? ` (${param.type})` : ''}`;
                    const paramDescription = param.description || '';
                    const inputPortName = `input_${index + 1}`;
                    const isConnected = node.inputs[inputPortName] && node.inputs[inputPortName].connections.length > 0;

                    const inputContainer = document.createElement('div');
                    if (paramDescription) {
                        const descEl = document.createElement('p');
                        descEl.className = 'field-description muted';
                        descEl.style.margin = '0 0 4px 0';
                        descEl.textContent = paramDescription;
                        inputContainer.appendChild(descEl);
                    }

                    let field;

                    if (param.type === 'boolean') {
                        const switchWrapper = document.createElement('label');
                        switchWrapper.className = 'switch-toggle';
                        const value = isConnected ? false : (currentData[paramName] ?? (param.default ?? false));
                        const input = createInput('checkbox', '', null);
                        input.dataset.paramName = paramName;
                        input.checked = !!value;
                        input.disabled = isConnected;
                        const slider = document.createElement('span');
                        slider.className = 'slider';
                        switchWrapper.append(input, slider);
                        inputContainer.appendChild(switchWrapper);

                        field = document.createElement('div');
                        field.className = 'field checkbox-field';
                        const label = document.createElement('label');
                        label.className = 'checkbox-label';
                        label.textContent = paramLabel;
                        field.appendChild(label);
                        field.appendChild(inputContainer);

                    } else if (Array.isArray(param.choices) && param.choices.length > 0) {
                        const value = isConnected
                            ? ''
                            : (currentData[paramName] ?? (param.default ?? ''));
                        const select = document.createElement('select');
                        select.dataset.paramName = paramName;
                        select.disabled = isConnected;

                        if (!param.required) {
                            const placeholderOption = document.createElement('option');
                            placeholderOption.value = '';
                            placeholderOption.textContent = '（请选择）';
                            select.appendChild(placeholderOption);
                        }

                        (param.choices || []).forEach(choice => {
                            const optionEl = document.createElement('option');
                            optionEl.value = choice.value ?? '';
                            optionEl.textContent = choice.label ?? choice.value ?? '';
                            select.appendChild(optionEl);
                        });

                        if (!select.value) {
                            select.value = value || '';
                        } else {
                            select.value = value || select.value;
                        }

                        inputContainer.appendChild(select);

                        field = createField(paramLabel, inputContainer);
                    } else if (param.type === 'button') {
                        const value = isConnected
                            ? ''
                            : (currentData[paramName] ?? (param.default ?? ''));
                        const select = createSelect(value, cachedButtonOptions, null);
                        select.dataset.paramName = paramName;
                        select.disabled = isConnected;
                        inputContainer.appendChild(select);

                        if (isConnected) {
                            const connectedNotice = document.createElement('p');
                            connectedNotice.className = 'field-description muted';
                            connectedNotice.style.margin = '4px 0 0 0';
                            connectedNotice.textContent = '值由上游节点提供';
                            inputContainer.appendChild(connectedNotice);
                        } else if (!cachedButtonOptions.length) {
                            const emptyHint = document.createElement('p');
                            emptyHint.className = 'field-description muted';
                            emptyHint.style.margin = '4px 0 0 0';
                            emptyHint.textContent = '当前没有可用的按钮，请先在“按钮”页面创建或保存一个按钮。';
                            inputContainer.appendChild(emptyHint);
                        } else {
                            const hint = document.createElement('p');
                            hint.className = 'field-description muted';
                            hint.style.margin = '4px 0 0 0';
                            hint.textContent = '列表会展示所有现有按钮，包含所属菜单与 ID，便于快速匹配。';
                            inputContainer.appendChild(hint);
                        }

                        field = createField(paramLabel, inputContainer);
                    } else {
                        const value = isConnected ? '' : (currentData[paramName] ?? (param.default ?? ''));
                        const placeholder = isConnected ? '值由上游节点提供' : (param.placeholder || '');
                        const input = createTextarea(value, null);
                        input.dataset.paramName = paramName;
                        input.disabled = isConnected;
                        input.placeholder = placeholder;
                        inputContainer.appendChild(input);
                        field = createField(paramLabel, inputContainer);
                    }

                    if (isConnected) {
                        const connectedNotice = document.createElement('p');
                        connectedNotice.className = 'field-description muted';
                        connectedNotice.style.margin = '4px 0 0 0';
                        connectedNotice.textContent = '值由上游节点提供';
                        inputContainer.appendChild(connectedNotice);
                    }

                    body.appendChild(field);
                });
            }

            if (actionOutputs && actionOutputs.length > 0) {
                const outputsHeader = document.createElement('h4');
                outputsHeader.textContent = '输出端口';
                outputsHeader.style.borderTop = '1px solid var(--border-color)';
                outputsHeader.style.paddingTop = '12px';
                outputsHeader.style.marginTop = '16px';
                body.appendChild(outputsHeader);

                actionOutputs.forEach(output => {
                    const outputContainer = document.createElement('div');
                    const descEl = document.createElement('p');
                    descEl.className = 'field-description muted';
                    descEl.style.margin = '0';
                    descEl.textContent = output.description || '无描述';
                    outputContainer.appendChild(descEl);

                    const field = createField(output.name, outputContainer);
                    field.style.alignItems = 'flex-start';
                    body.appendChild(field);
                });
            }
        }

        const footer = document.createElement('div');
        footer.style.cssText = "width: 100%; display: flex; justify-content: flex-end; gap: 12px;";

        const cancelBtn = document.createElement('button');
        cancelBtn.textContent = '取消';
        cancelBtn.className = 'secondary';
        cancelBtn.onclick = closeModal;

        const saveBtn = document.createElement('button');
        saveBtn.textContent = '保存';
        saveBtn.onclick = () => {
            const finalData = { ...currentData };

            // 错误修复：同时查询 textarea 和 checkbox，以正确保存状态。
            body.querySelectorAll('[data-param-name]').forEach(input => {
                const key = input.dataset.paramName;
                if (!key) return;

                if (input.disabled) {
                    delete finalData[key];
                    return;
                }

                if (input.tagName === 'INPUT' && input.type === 'checkbox') {
                    finalData[key] = input.checked;
                    return;
                }

                if (input.tagName === 'SELECT') {
                    if (input.value) {
                        finalData[key] = input.value;
                    } else {
                        delete finalData[key];
                    }
                    return;
                }

                finalData[key] = input.value;
            });

            if (conditionMode === 'none') {
                delete finalData.__condition__;
            } else if (conditionMode === 'boolean') {
                finalData.__condition__ = conditionBoolValue;
            } else if (conditionMode === 'linked') {
                if (!linkedConditionTarget) {
                    showInfoModal('请选择一个布尔连线作为条件。', true);
                    return;
                }
                const linkedPayload = {
                    type: 'input',
                    name: linkedConditionTarget,
                };
                if (linkedConditionNegate) {
                    linkedPayload.negate = true;
                }
                finalData.__condition__ = linkedPayload;
            } else if (conditionMode === 'template') {
                const trimmed = (conditionTemplateValue || '').trim();
                if (!trimmed) {
                    showInfoModal('模板条件不能为空，请填写表达式后再保存。', true);
                    return;
                }
                finalData.__condition__ = trimmed;
            } else if (conditionMode === 'json') {
                const raw = conditionJsonValue || '';
                if (!raw.trim()) {
                    delete finalData.__condition__;
                } else {
                    try {
                        finalData.__condition__ = JSON.parse(raw);
                    } catch (err) {
                        showInfoModal(`保存失败：条件配置不是有效的 JSON。\n\n${err.message}`, true);
                        return;
                    }
                }
            }

            if (window.tgButtonEditor && window.tgButtonEditor.updateNodeConfig) {
                window.tgButtonEditor.updateNodeConfig(node.id, finalData);
            } else {
                console.error("错误: editor.js 没有提供 updateNodeConfig 函数。");
            }

            closeModal();
        };

        footer.append(cancelBtn, saveBtn);
        openModal(title, body, footer);
    }

    // --- 辅助函数与初始化 ---
    function createField(labelText, inputEl) { const field = document.createElement('div'); field.className = 'field'; field.innerHTML = `<label>${labelText}</label>`; field.appendChild(inputEl); return field; }
    function createInput(type, value, onChange) { const input = document.createElement('input'); input.type = type; input.value = value ?? ''; if (onChange) input.oninput = e => onChange(e.target.value); return input; }
    function createSelect(value, options, onChange) { const select = document.createElement('select'); select.innerHTML = `<option value="">（请选择）</option>` + (options || []).map(opt => `<option value="${opt.value}">${opt.label}</option>`).join(''); select.value = value ?? ''; if (onChange) select.onchange = e => onChange(e.target.value); return select; }
    function createTextarea(value, onChange) { const textarea = document.createElement('textarea'); textarea.value = value; if (onChange) textarea.oninput = e => onChange(e.target.value); return textarea; }
    function getMenuOptions(excludeId = null) { return Object.keys(state.menus).filter(id => id !== excludeId).map(id => ({ value: id, label: `${state.menus[id].name} (${id})` })); }
    async function generateId(kind) { return (await api('/api/util/ids', { method: 'POST', body: { type: kind } })).id; }

    function updateTabIndicator(target, animate = true) {
        const indicator = document.getElementById('tabIndicator');
        const nav = document.querySelector('.tab-nav');
        if (!target || !indicator || !nav) return;

        if (!animate) {
            indicator.style.transition = 'none';
        }

        const navRect = nav.getBoundingClientRect();
        const targetRect = target.getBoundingClientRect();

        indicator.style.left = `${targetRect.left - navRect.left}px`;
        indicator.style.width = `${targetRect.width}px`;

        if (!animate) {
            void indicator.offsetWidth; // 强制重排以应用即时位置
            indicator.style.transition = ''; // 为将来的点击恢复过渡效果
        }
    }

    // --- 事件监听器 ---
    document.getElementById('drawflow').addEventListener('opennodeconfig', (e) => {
        if (e.detail && e.detail.node) {
            openNodeConfigModal(e.detail.node);
        }
    });

    addMenuBtn.onclick = async () => { const id = await generateId('menu'); state.menus[id] = { id, name: '新菜单', header: '新菜单标题', items: [] }; renderAll(); };
    addUnassignedBtn.onclick = () => openButtonEditor(null, null);
    addActionBtn.onclick = async () => { const id = await generateId('action'); state.actions[id] = { id, name: '新动作', kind: 'http', config: { request: { method: 'GET', url: 'https://' } } }; renderAll({ openNewId: id, type: 'action' }); };
    addWebappBtn.onclick = async () => { const id = await generateId('webapp'); state.web_apps = state.web_apps || {}; state.web_apps[id] = { id, name: '新WebApp', kind: 'external', url: 'https://' }; renderAll({ openNewId: id, type: 'webapp' }); };
    refreshBtn.onclick = () => loadState().catch(err => showInfoModal(err.message, true));
    saveBtn.onclick = async () => {
        // 首先，验证主界面中所有可见的 JSON 文本区域
        const actionConfigTextareas = document.querySelectorAll('#actionsContainer .json-config-input');
        for (const textarea of actionConfigTextareas) {
            try {
                JSON.parse(textarea.value);
            } catch (e) {
                const details = textarea.closest('details');
                const id = details ? details.dataset.id : '未知';
                showInfoModal(`保存失败！\n动作 “${id}” 的配置 (JSON) 格式错误，请修正后再保存。\n\n${e.message}`, true);
                if (details) details.open = true;
                textarea.focus();
                return;
            }
        }

        try {
            // 步骤 1: 通知编辑器保存其当前状态。如果需要，它会提示输入名称。
            // 这将返回一个 promise，当用户提供名称或取消时，该 promise 会被解析。
            const savePromise = window.tgButtonEditor.saveCurrentWorkflow();

            // 无论成功还是失败，我们都会继续，因为用户可能会取消提示。
            savePromise.then(async () => {
                // 步骤 2: 既然编辑器的潜在更改已提交到服务器，
                // 获取所有工作流的最终列表。
                const workflowsFromServer = await api('/api/workflows');
                state.workflows = workflowsFromServer;

                // 步骤 3: 保存整个现已完全一致的应用程序状态。
                await api('/api/state', { method: 'PUT', body: state });
                showInfoModal('保存成功！');
            }).catch(error => {
                // 这里会捕获来自 saveCurrentWorkflow 的错误（例如，用户取消提示）
                // 或来自后续的 API 调用。
                showInfoModal(`操作被中断或失败: ${error.message}`, true);
            });
        } catch (err) {
            showInfoModal(`保存失败: ${err.message}`, true);
        }
    };
    exportBtn.onclick = () => { const blob = new Blob([JSON.stringify(state, null, 2)], { type: 'application/json' }); const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'tg_button_config.json'; a.click(); URL.revokeObjectURL(a.href); };
        document.querySelector('.tab-nav').addEventListener('click', (e) => {
        const targetLink = e.target.closest('.tab-link');
        if (targetLink && !targetLink.classList.contains('active')) {
            const tabId = targetLink.dataset.tab;
            localStorage.setItem('tgButtonActiveTab', tabId); // 保存当前标签页


            const newContent = document.getElementById(tabId);
            const activeContent = document.querySelector('.tab-content.active');

            // 立即更新链接并触Indicators动画
            document.querySelectorAll('.tab-link').forEach(link => link.classList.remove('active'));
            targetLink.classList.add('active');
            updateTabIndicator(targetLink);

            // 新的、可靠的、使用 setTimeout 的淡出逻辑
            if (activeContent) {
                activeContent.classList.remove('active'); // 开始淡出
            }

            setTimeout(() => {
                if (activeContent) {
                    activeContent.style.display = 'none'; // 淡出后隐藏旧内容
                }
                if (newContent) {
                    newContent.style.display = 'block'; // 准备新内容
                    // 一个微小的延迟，以确保在开始淡入之前应用 'display: block'
                    setTimeout(() => newContent.classList.add('active'), 10);
                }
            }, 300); // 等待 CSS 过渡完成 (0.3秒)
        }
    });

    window.addEventListener('resize', () => updateTabIndicator(document.querySelector('.tab-link.active'), false));

    // --- 用于监听来自编辑器的工作流更新的事件 ---
    window.addEventListener('workflowsUpdated', async () => {
        try {
            const workflowsFromServer = await api('/api/workflows');
            state.workflows = workflowsFromServer;
            console.log('Workflow list updated automatically in main state.');
        } catch (err) {
            console.error('Failed to refresh workflows after update:', err);
        }
    });

    // --- 初始加载 ---
    loadState()
        .then(() => {
            // -- 恢复上次打开的标签页 --
            const savedTabId = localStorage.getItem('tgButtonActiveTab');
            if (savedTabId) {
                const targetLink = document.querySelector(`.tab-link[data-tab="${savedTabId}"]`);
                const newContent = document.getElementById(savedTabId);

                if (targetLink && newContent) {
                    // 移除默认的 active 状态
                    const defaultActiveLink = document.querySelector('.tab-link.active');
                    const defaultActiveContent = document.querySelector('.tab-content.active');
                    if(defaultActiveLink) defaultActiveLink.classList.remove('active');
                    if(defaultActiveContent) {
                       defaultActiveContent.classList.remove('active');
                       defaultActiveContent.style.display = 'none';
                    }

                    // 设置新的 active 状态
                    targetLink.classList.add('active');
                    newContent.style.display = 'block';
                    newContent.classList.add('active');
                }
            }
            // -- 结束恢复 --

            // 设置指示器的初始位置，无动画
            updateTabIndicator(document.querySelector('.tab-link.active'), false);
        })
        .catch(err => console.error('Failed to load initial state:', err));
}());
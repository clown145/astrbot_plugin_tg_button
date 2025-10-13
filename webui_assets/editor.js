window.addEventListener('DOMContentLoaded', () => {
    const container = document.getElementById('drawflow');
    if (!container) {
        console.error('Drawflow container #drawflow not found!');
        return;
    }

    const editor = new Drawflow(container);
    editor.start();

    const nodePalette = document.getElementById('node-palette');
    if (!nodePalette) {
        console.error('Node palette #node-palette not found!');
        return;
    }

    // --- 认证与 API 辅助函数 ---
    const getAuthToken = () => localStorage.getItem('tg-button-auth-token');

    const fetchWithAuth = async (url, options = {}) => {
        const token = getAuthToken();
        const headers = new Headers(options.headers || {});
        if (token) {
            headers.append('X-Auth-Token', token);
        }

        const response = await fetch(url, { ...options, headers });

        if (!response.ok) {
            if (response.status === 401) {
                localStorage.removeItem('tg-button-auth-token');
                window.location.href = '/login';
                throw new Error('认证失败，请重新登录。');
            }
            const errorData = await response.json().catch(() => ({ error: `HTTP error! status: ${response.status}` }));
            throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
        }

        return response;
    };

    // --- 节点面板逻辑 ---
    let allAvailableActions = {};
    const populateNodePalette = (actions) => {
        allAvailableActions = actions; // 存储所有可用动作，供 loadWorkflow 使用
        if (!nodePalette) return;
        nodePalette.innerHTML = ''; // 清空

        if (!actions || typeof actions !== 'object') {
            nodePalette.innerHTML = '<p style="color: red;">动作列表数据无效。</p>';
            return;
        }

        // 仅筛选模块化动作
        const modularActions = Object.entries(actions).filter(([_, action]) => action.isModular);

        if (modularActions.length === 0) {
            nodePalette.innerHTML = '<p class="muted">没有可用的模块化动作。</p>';
            return;
        }

        const createNodeElement = (actionId, action) => {
            const nodeElement = document.createElement('div');
            nodeElement.className = 'palette-node';
            nodeElement.draggable = true;

            // 为节点构建富 HTML，包括模块化动作的端口
            let nodeTitleHTML = `
              <div style="display: flex; justify-content: space-between; align-items: center;">
                <strong>${action.name || actionId}</strong>
                <a href="/api/actions/modular/download/${action.id}" download="${action.filename || (action.id + '.py')}" class="secondary" style="font-size: 0.8em; padding: 2px 6px; text-decoration: none;">下载</a>
              </div>
            `;
            let nodeHTML = nodeTitleHTML;
            if (action.isModular) {
                const inputsHTML = (action.inputs || []).map(input => `<div class="port-label">- ${input.name} (in)</div>`).join('');
                const outputsHTML = (action.outputs || []).map(output => `<div class="port-label">- ${output.name} (out)</div>`).join('');
                nodeHTML += `<div class="node-ports">${inputsHTML}${outputsHTML}</div>`;
            }
            nodeHTML += `<p>${action.description || '无描述'}</p>`;
            nodeElement.innerHTML = nodeHTML;

            nodeElement.addEventListener('dragstart', (event) => {
                if (event.dataTransfer) {
                    // 传递完整的动作对象，以便在放置时获取输入/输出信息
                    event.dataTransfer.setData('text/plain', JSON.stringify(action));
                }
            });

            return nodeElement;
        };

        const modularHeader = document.createElement('h4');
        modularHeader.textContent = '模块化动作';

        // --- 上传按钮 ---
        const uploadBtn = document.createElement('button');
        uploadBtn.textContent = '上传';
        uploadBtn.className = 'secondary';
        uploadBtn.style.marginLeft = '10px';
        uploadBtn.style.fontSize = '0.8em';
        modularHeader.appendChild(uploadBtn);

        const fileInput = document.createElement('input');
        fileInput.type = 'file';
        fileInput.accept = '.py';
        fileInput.style.display = 'none';

        uploadBtn.addEventListener('click', () => fileInput.click());

        fileInput.addEventListener('change', (event) => {
            const file = event.target.files[0];
            if (!file) return;

            const reader = new FileReader();
            reader.onload = async (e) => {
                const content = e.target.result;
                try {
                    const response = await fetchWithAuth('/api/actions/modular/upload', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ filename: file.name, content })
                    });
                    if (!response.ok) {
                        const err = await response.json();
                        throw new Error(err.error || '上传失败');
                    }
                    window.showInfoModal(`动作 '${file.name}' 上传成功！`);
                    // 刷新面板
                    const actionsResponse = await fetchWithAuth('/api/actions/modular/available');
                    const actionsData = await actionsResponse.json();
                    // main.js 也会获取本地动作，我们需要合并它们
                    const localActionsResponse = await fetchWithAuth('/api/actions/local/available');
                    const localActionsData = await localActionsResponse.json();

                    const combinedActions = { ...actionsData.actions, ...localActionsData.actions };
                    window.tgButtonEditor.refreshPalette(combinedActions);
                } catch (error) {
                    console.error('上传动作失败:', error);
                    window.showInfoModal(`上传失败: ${error.message}`, true);
                }
            };
            reader.readAsText(file);
            // 重置输入值，以便可以再次上传相同的文件
            event.target.value = '';
        });
        // --- 上传按钮结束 ---

        nodePalette.appendChild(modularHeader);
        nodePalette.appendChild(fileInput); // 将隐藏的 input 添加到 DOM

        modularActions.forEach(([actionId, action]) => {
            nodePalette.appendChild(createNodeElement(actionId, { ...action, id: actionId }));
        });
    };

    // --- 拖放逻辑 ---
    container.addEventListener('drop', (event) => {
        event.preventDefault();
        if (event.dataTransfer) {
            const actionStr = event.dataTransfer.getData('text/plain');
            if (actionStr) {
                try {
                    const action = JSON.parse(actionStr);

                    const numInputs = action.isModular ? (action.inputs || []).length : 1;
                    const numOutputs = action.isModular ? (action.outputs || []).length : 1;

                    const pos_x = event.clientX * (editor.precanvas.clientWidth / (editor.precanvas.clientWidth * editor.zoom)) - (editor.precanvas.getBoundingClientRect().x * (editor.precanvas.clientWidth / (editor.precanvas.clientWidth * editor.zoom)));
                    const pos_y = event.clientY * (editor.precanvas.clientHeight / (editor.precanvas.clientHeight * editor.zoom)) - (editor.precanvas.getBoundingClientRect().y * (editor.precanvas.clientHeight / (editor.precanvas.clientHeight * editor.zoom)));

                    // 为画布上的节点构建更丰富的内部 HTML
                    const inputsHTML = (action.inputs || []).map(input => `<div class="port-label port-label-in">${input.name}</div>`).join('');
                    const outputsHTML = (action.outputs || []).map(output => `<div class="port-label port-label-out">${output.name}</div>`).join('');

                    const nodeContentHTML = `
                        <div class="node-title">${action.name || action.id}</div>
                        ${action.isModular ? `<div class="node-ports-container">${inputsHTML}${outputsHTML}</div>` : ''}
                    `;

                    const internalNodeData = {
                        action: action, // 将整个动作定义存储在节点数据中
                        data: {} // 初始化用于配置的空数据
                    };

                    editor.addNode(
                        action.id,       // 节点类型名称
                        Math.max(1, numInputs),  // 确保至少有一个输入端口
                        Math.max(1, numOutputs), // 确保至少有一个输出端口
                        pos_x,
                        pos_y,
                        'workflow-node', // 用于样式的新 CSS 类
                        internalNodeData,
                        nodeContentHTML
                    );

                } catch (e) {
                    console.error("Failed to parse node data on drop", e);
                }
            }
        }
    });
    container.addEventListener('dragover', (event) => event.preventDefault());

    // --- 保存和加载工作流逻辑 ---
    const workflowNameInput = document.getElementById('workflowNameInput');
    const workflowDescriptionInput = document.getElementById('workflowDescriptionInput');
    const newWorkflowBtn = document.getElementById('newWorkflowBtn');
    const workflowSelector = document.getElementById('workflowSelector');
    const deleteWorkflowBtn = document.getElementById('deleteWorkflowBtn');
    const saveWorkflowBtn = document.getElementById('saveWorkflowBtn');

    const populateWorkflowSelector = async () => {
        try {
            const response = await fetchWithAuth('/api/workflows');
            if (!response.ok) throw new Error('Failed to fetch workflows');
            const workflows = await response.json();

            const selectedValue = workflowSelector.value;
            workflowSelector.innerHTML = '<option value="">-- 选择工作流 --</option>';

            Object.keys(workflows).forEach(id => {
                const option = document.createElement('option');
                option.value = id;
                option.textContent = (workflows[id] && workflows[id].name) ? workflows[id].name : id;
                workflowSelector.appendChild(option);
            });

            if (workflows[selectedValue]) {
                workflowSelector.value = selectedValue;
            }
        } catch (error) {
            console.error('Error populating workflow selector:', error);
        }
    };

    const saveWorkflow = async (isAutoSave = false) => {
        let workflowId = editor.currentWorkflowId;
        const workflowName = workflowNameInput.value.trim();
        const workflowDescription = workflowDescriptionInput.value.trim();

        if (!workflowName) {
            if (isAutoSave && !workflowId && editor.getNodesFromName("").length === 0) {
                 return Promise.resolve();
            }
            window.showInfoModal("工作流名称不能为空。", true);
            workflowNameInput.focus();
            return Promise.reject(new Error("Workflow name cannot be empty."));
        }

        // 如果是新工作流，则根据名称生成 ID。但如果 ID 已存在，则绝不更改。
        if (!workflowId) {
             let sanitizedId = workflowName.trim().replace(/\s+/g, '-').replace(/[^a-zA-Z0-9-._~]/g, '');
            if (!sanitizedId) {
                // 如果名称仅包含无效字符（如中文），
                // 则对原始名称进行编码以创建 URL 安全的 ID。
                sanitizedId = encodeURIComponent(workflowName.trim());
            }
            workflowId = sanitizedId;

            if (!workflowId) { // 最后检查一下，以防名称只是空格
                window.showInfoModal("工作流名称无效，请输入有效字符。", true);
                workflowNameInput.focus();
                return Promise.reject(new Error("Invalid workflow name."));
            }
        }

        const drawflowData = editor.export();

        // --- 转换为我们的自定义格式 ---
        const customFormat = {
            id: workflowId,
            name: workflowName,
            description: workflowDescription,
            nodes: {},
            edges: []
        };

        const dfNodes = (drawflowData.drawflow.Home || drawflowData.drawflow.main).data;
        for (const dfNodeId in dfNodes) {
            const dfNode = dfNodes[dfNodeId];
            const action = dfNode.data.action;

            if (!action) {
                console.warn(`节点 ${dfNodeId} 缺少动作数据，将被跳过。`);
                continue;
            }

            customFormat.nodes[dfNode.id] = {
                id: dfNode.id.toString(),
                action_id: action.id,
                position: { x: dfNode.pos_x, y: dfNode.pos_y },
                data: dfNode.data.data || {} // 持久化已配置的数据
            };

            for (const outputPort in dfNode.outputs) {
                const sourceOutputIndex = parseInt(outputPort.replace('output_', ''), 10) - 1;
                if (isNaN(sourceOutputIndex)) continue;

                dfNode.outputs[outputPort].connections.forEach(conn => {
                    const targetNode = dfNodes[conn.node];
                    if (!targetNode) return;

                    const targetInputIndex = parseInt(conn.output.replace('input_', ''), 10) - 1;
                    if (isNaN(targetInputIndex)) return;

                    const sourceOutputName = (action.outputs && action.outputs[sourceOutputIndex])
                        ? action.outputs[sourceOutputIndex].name
                        : `output_${sourceOutputIndex + 1}`;

                    const targetAction = targetNode.data.action;
                    const targetInputName = (targetAction && targetAction.inputs && targetAction.inputs[targetInputIndex])
                        ? targetAction.inputs[targetInputIndex].name
                        : `input_${targetInputIndex + 1}`;

                    customFormat.edges.push({
                        id: `edge-${dfNode.id}-${targetNode.id}-${sourceOutputIndex}-${targetInputIndex}`,
                        source_node: dfNode.id.toString(),
                        source_output: sourceOutputName,
                        target_node: targetNode.id.toString(),
                        target_input: targetInputName
                    });
                });
            }
        }
        // --- 转换结束 ---

        try {
            const response = await fetchWithAuth(`/api/workflows/${workflowId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(customFormat) // 发送我们的新格式
            });
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({ error: response.statusText }));
                throw new Error(`保存失败: ${errorData.error}`);
            }

            if (!isAutoSave) {
                window.showInfoModal(`工作流 “${workflowName}” 已保存！`);
            }

            editor.currentWorkflowId = workflowId;
            await populateWorkflowSelector();
            workflowSelector.value = workflowId;

            // 通知主应用工作流已更改
            window.dispatchEvent(new CustomEvent('workflowsUpdated'));

            return Promise.resolve();
        } catch (error) {
            console.error('Error saving workflow:', error);
            if (!isAutoSave) {
                window.showInfoModal(error.message, true);
            }
            return Promise.reject(error);
        }
    };

    const loadWorkflow = async (workflowId) => {
        if (!workflowId) return;
        try {
            const response = await fetchWithAuth(`/api/workflows/${workflowId}`);
            if (!response.ok) throw new Error('加载工作流失败');
            const customData = await response.json();

            editor.clear();
            editor.currentWorkflowId = workflowId;
            workflowNameInput.value = customData.name || '';
            workflowDescriptionInput.value = customData.description || '';

            // ID 映射：从自定义字符串 ID（例如，“node-1”）到 Drawflow 的内部整数 ID
            const nodeIdMap = new Map();

            // 步骤 1：添加所有节点并创建 ID 映射
            for (const customNodeId in customData.nodes) {
                const customNode = customData.nodes[customNodeId];
                const action = allAvailableActions[customNode.action_id];

                if (!action) {
                    console.warn(`未找到 ID 为 ${customNode.action_id} 的动作定义，节点 ${customNodeId} 将被跳过。`);
                    continue;
                }

                const numInputs = action.isModular ? (action.inputs || []).length : 1;
                const numOutputs = action.isModular ? (action.outputs || []).length : 1;

                const inputsHTML = (action.inputs || []).map(input => `<div class="port-label port-label-in">${input.name}</div>`).join('');
                const outputsHTML = (action.outputs || []).map(output => `<div class="port-label port-label-out">${output.name}</div>`).join('');

                const nodeContentHTML = `
                    <div class="node-title">${action.name || action.id}</div>
                    ${action.isModular ? `<div class="node-ports-container">${inputsHTML}${outputsHTML}</div>` : ''}
                `;

                const internalNodeData = {
                    action: { ...action, id: customNode.action_id },
                    data: customNode.data || {} // 恢复已配置的数据
                };

                const drawflowId = editor.addNode(
                    customNode.action_id, // 节点名称
                    Math.max(1, numInputs),
                    Math.max(1, numOutputs),
                    customNode.position.x,
                    customNode.position.y,
                    'workflow-node',
                    internalNodeData,
                    nodeContentHTML,
                    false // 'typenode' -> false 表示使用 html 内容
                );

                nodeIdMap.set(customNode.id, drawflowId);
            }

            // 步骤 2：使用映射的 ID 添加所有连接
            (customData.edges || []).forEach(edge => {
                const sourceDrawflowId = nodeIdMap.get(edge.source_node);
                const targetDrawflowId = nodeIdMap.get(edge.target_node);

                if (sourceDrawflowId === undefined || targetDrawflowId === undefined) {
                     console.warn(`无法创建连接，因为找不到源节点或目标节点: ${edge.id}`);
                     return;
                }

                // 查找动作定义以获取正确的端口索引
                const sourceCustomNode = customData.nodes[edge.source_node];
                const targetCustomNode = customData.nodes[edge.target_node];

                if (!sourceCustomNode || !targetCustomNode) return;

                const sourceAction = allAvailableActions[sourceCustomNode.action_id];
                const targetAction = allAvailableActions[targetCustomNode.action_id];

                if (!sourceAction || !targetAction) return;

                const sourceOutputIndex = sourceAction.isModular
                    ? (sourceAction.outputs || []).findIndex(o => o.name === edge.source_output)
                    : (edge.source_output === 'output' ? 0 : -1); // 旧版动作的回退

                const targetInputIndex = targetAction.isModular
                    ? (targetAction.inputs || []).findIndex(i => i.name === edge.target_input)
                    : (edge.target_input === 'input' ? 0 : -1); // 旧版动作的回退

                if (sourceOutputIndex === -1 || targetInputIndex === -1) {
                    console.warn(`无法找到连接端口: ${edge.id}`);
                    return;
                }

                const sourcePort = `output_${sourceOutputIndex + 1}`;
                const targetPort = `input_${targetInputIndex + 1}`;

                editor.addConnection(sourceDrawflowId, targetDrawflowId, sourcePort, targetPort);
            });

        } catch (error) {
            console.error(`加载工作流 '${workflowId}' 时出错:`, error);
            alert('加载失败，请查看控制台日志。');
        }
    };

    const deleteWorkflow = async () => {
        const workflowId = workflowSelector.value;
        if (!workflowId) return alert('请先选择一个要删除的工作流。');

        const selectedOption = workflowSelector.querySelector(`option[value="${workflowId}"]`);
        const workflowNameToDelete = selectedOption ? selectedOption.textContent : workflowId;

        // 使用自定义确认模态框
        window.showConfirmModal(
            '确认删除',
            `您确定要永久删除工作流 “${workflowNameToDelete}” 吗？<br><br>此操作无法撤销。`,
            async () => {
                // 此代码仅在用户单击“确认”时运行
                try {
                    const response = await fetchWithAuth(`/api/workflows/${workflowId}`, { method: 'DELETE' });
                    if (!response.ok) {
                        const errorData = await response.json().catch(() => ({ error: response.statusText }));
                        throw new Error(`删除失败: ${errorData.error || 'Unknown error'}`);
                    }
                    window.showInfoModal(`工作流 “${workflowNameToDelete}” 已删除。`);

                    if (editor.currentWorkflowId === workflowId) {
                        editor.clear();
                        delete editor.currentWorkflowId;
                        workflowNameInput.value = '';
                        workflowDescriptionInput.value = '';
                    }
                    await populateWorkflowSelector();
                } catch (error) {
                    console.error(`Error deleting workflow '${workflowId}':`, error);
                    window.showInfoModal(error.message, true);
                }
            }
        );
    };

    const handleLoadWorkflow = () => {
        const workflowId = workflowSelector.value;
        const previousWorkflowId = editor.currentWorkflowId || "";
        if (workflowId) {
            const isDirty = (editor.getNodesFromName("").length > 0 || workflowNameInput.value) && editor.currentWorkflowId !== workflowId;
            if (isDirty) {
                window.showConfirmModal(
                    '确认加载',
                    '加载新工作流将覆盖当前未保存的更改，确定要加载吗？',
                    () => loadWorkflow(workflowId), // onConfirm：加载新的
                    () => { workflowSelector.value = previousWorkflowId; } // onCancel：恢复选择器
                );
            } else {
                loadWorkflow(workflowId); // 不脏，直接加载
            }
        }
    };

    // --- 节点配置的事件监听器 ---
    container.addEventListener('dblclick', (event) => {
        // 确保单击的是节点主体，而不是输入/输出端口。
        const target = event.target;
        if (target.closest('.drawflow-node') && !target.closest('.input') && !target.closest('.output')) {
            const nodeElement = target.closest('.drawflow-node');
            const nodeId = nodeElement.id.split('-')[1];

            if (nodeId) {
                const node = editor.getNodeFromId(nodeId);
                // 分派一个自定义事件，由主 UI 脚本处理
                container.dispatchEvent(new CustomEvent('opennodeconfig', {
                    bubbles: true,
                    detail: { node: node }
                }));
            }
        }
    });

    const handleNewWorkflow = () => {
        const isDirty = editor.getNodesFromName("").length > 0 || workflowNameInput.value;
        if (isDirty) {
            window.showConfirmModal(
                '确认新建',
                '您确定要新建工作流吗？<br><br>当前画布上的所有未保存的更改都将丢失。'
                , () => {
                    editor.clear();
                    delete editor.currentWorkflowId;
                    workflowSelector.value = ""; // 重置下拉菜单
                    workflowNameInput.value = "";
                    workflowDescriptionInput.value = "";
                }
            );
        } else {
            // 如果不脏，则无需确认即可清除
            editor.clear();
            delete editor.currentWorkflowId;
            workflowSelector.value = "";
            workflowNameInput.value = "";
            workflowDescriptionInput.value = "";
        }
    };

    newWorkflowBtn.addEventListener('click', handleNewWorkflow);
    workflowSelector.addEventListener('change', handleLoadWorkflow);
    deleteWorkflowBtn.addEventListener('click', deleteWorkflow);
    saveWorkflowBtn.addEventListener('click', () => saveWorkflow(false));

    // --- 为主应用暴露的全局函数 ---
    window.tgButtonEditor = {
        refreshPalette: (actions) => populateNodePalette(actions),
        refreshWorkflows: populateWorkflowSelector,
        saveCurrentWorkflow: () => saveWorkflow(true),
        updateNodeConfig: (nodeId, newData) => {
            const node = editor.getNodeFromId(nodeId);
            if (node && node.data) {
                // 更新用于配置的特定“data”属性
                const newInternalData = { ...node.data, data: newData };
                editor.updateNodeDataFromId(nodeId, newInternalData);
            } else {
                console.error(`尝试更新节点配置失败: 未找到 ID 为 ${nodeId} 的节点。`);
            }
        }
    };

    // --- 初始化 ---
    populateWorkflowSelector(); // 初始加载工作流
    console.log('Workflow editor script loaded. Waiting for main app to provide action palette.');
});
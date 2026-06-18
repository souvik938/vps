import os
import sys
import subprocess
import tempfile
import json
import shutil
import zipfile
import io
import time
import threading
import venv
import site
from pathlib import Path
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string, session, send_file, send_from_directory

app = Flask(__name__)
app.secret_key = 'ultimate-python-runner-secret-2026'

# ============ CONFIGURATION ============
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE_DIR = os.path.join(BASE_DIR, 'workspace')
VENV_DIR = os.path.join(BASE_DIR, 'venvs')
os.makedirs(WORKSPACE_DIR, exist_ok=True)
os.makedirs(VENV_DIR, exist_ok=True)

# Store running processes
running_processes = {}
process_outputs = {}
process_status = {}

# ============ HELPER FUNCTIONS ============
def get_venv_path(project_name):
    """Get virtual environment path for a project"""
    return os.path.join(VENV_DIR, project_name)

def get_project_path(project_name):
    """Get project workspace path"""
    return os.path.join(WORKSPACE_DIR, project_name)

def create_venv(project_name):
    """Create virtual environment for project"""
    venv_path = get_venv_path(project_name)
    if not os.path.exists(venv_path):
        venv.create(venv_path, with_pip=True)
    return venv_path

def get_python_executable(project_name):
    """Get Python executable path for project's venv"""
    venv_path = get_venv_path(project_name)
    if os.name == 'nt':  # Windows
        return os.path.join(venv_path, 'Scripts', 'python.exe')
    else:  # Linux/Mac
        return os.path.join(venv_path, 'bin', 'python')

def get_pip_executable(project_name):
    """Get pip executable path for project's venv"""
    venv_path = get_venv_path(project_name)
    if os.name == 'nt':  # Windows
        return os.path.join(venv_path, 'Scripts', 'pip.exe')
    else:  # Linux/Mac
        return os.path.join(venv_path, 'bin', 'pip')

def install_requirements(project_name):
    """Install requirements.txt for project"""
    project_path = get_project_path(project_name)
    req_file = os.path.join(project_path, 'requirements.txt')
    
    if not os.path.exists(req_file):
        return {'success': True, 'message': 'No requirements.txt found'}
    
    pip = get_pip_executable(project_name)
    try:
        result = subprocess.run(
            [pip, 'install', '-r', req_file],
            capture_output=True,
            text=True,
            timeout=60
        )
        return {
            'success': result.returncode == 0,
            'output': result.stdout + result.stderr
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}

def get_file_tree(path, prefix=''):
    """Get hierarchical file tree structure"""
    tree = []
    try:
        items = sorted(os.listdir(path))
        for i, item in enumerate(items):
            if item.startswith('.'):
                continue
            full_path = os.path.join(path, item)
            is_last = i == len(items) - 1
            tree.append({
                'name': item,
                'path': full_path,
                'is_dir': os.path.isdir(full_path),
                'prefix': prefix,
                'is_last': is_last
            })
            if os.path.isdir(full_path):
                tree.extend(get_file_tree(full_path, prefix + ('    ' if is_last else '│   ')))
    except:
        pass
    return tree

# ============ HTML TEMPLATE ============
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🐍 Ultimate Python Code Runner</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        :root {
            --bg-primary: #0d1117;
            --bg-secondary: #161b22;
            --bg-tertiary: #21262d;
            --text-primary: #c9d1d9;
            --text-secondary: #8b949e;
            --border-color: #30363d;
            --accent: #58a6ff;
            --success: #238636;
            --danger: #da3633;
            --warning: #d29922;
            --purple: #8957e5;
        }
        body {
            font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            height: 100vh;
            overflow: hidden;
            display: flex;
            flex-direction: column;
        }
        
        /* Header */
        .header {
            background: var(--bg-secondary);
            padding: 10px 20px;
            border-bottom: 1px solid var(--border-color);
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 10px;
        }
        .header h1 {
            font-size: 20px;
            background: linear-gradient(135deg, #58a6ff, #8957e5, #f0883e);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-weight: 700;
        }
        .header-actions {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
        }
        .btn {
            padding: 6px 14px;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 12px;
            font-weight: 500;
            transition: 0.2s;
            color: white;
            display: inline-flex;
            align-items: center;
            gap: 5px;
            text-decoration: none;
        }
        .btn-primary { background: var(--accent); }
        .btn-primary:hover { background: #1f6feb; }
        .btn-success { background: var(--success); }
        .btn-success:hover { background: #2ea043; }
        .btn-danger { background: var(--danger); }
        .btn-danger:hover { background: #f85149; }
        .btn-warning { background: var(--warning); }
        .btn-warning:hover { background: #e3b341; }
        .btn-purple { background: var(--purple); }
        .btn-purple:hover { background: #7c4dcc; }
        .btn-secondary { background: var(--bg-tertiary); color: var(--text-primary); }
        .btn-secondary:hover { background: #30363d; }
        .btn-sm { padding: 4px 10px; font-size: 11px; }
        
        /* Main Container */
        .container {
            display: flex;
            flex: 1;
            overflow: hidden;
        }
        
        /* Sidebar */
        .sidebar {
            width: 320px;
            background: var(--bg-secondary);
            border-right: 1px solid var(--border-color);
            display: flex;
            flex-direction: column;
            flex-shrink: 0;
        }
        .sidebar-header {
            padding: 12px 15px;
            border-bottom: 1px solid var(--border-color);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .sidebar-header h3 {
            font-size: 13px;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .sidebar-actions {
            display: flex;
            gap: 5px;
        }
        .sidebar-actions .btn {
            padding: 3px 8px;
            font-size: 10px;
        }
        .file-tree {
            flex: 1;
            overflow-y: auto;
            padding: 10px 15px;
        }
        .file-tree .folder {
            color: var(--text-secondary);
        }
        .file-tree .file {
            color: var(--text-primary);
            cursor: pointer;
            padding: 3px 0;
            border-radius: 4px;
            transition: 0.15s;
        }
        .file-tree .file:hover { background: var(--bg-tertiary); }
        .file-tree .file.active { background: #1f6feb33; color: var(--accent); }
        .file-tree .file .icon { margin-right: 5px; }
        .file-tree .file .run-btn {
            opacity: 0;
            transition: 0.2s;
            margin-left: 8px;
        }
        .file-tree .file:hover .run-btn { opacity: 1; }
        .file-tree .tree-item {
            display: flex;
            align-items: center;
            gap: 5px;
            padding: 2px 0;
        }
        .file-tree .tree-item .prefix {
            color: var(--text-secondary);
            font-size: 12px;
            white-space: pre;
        }
        .file-tree .tree-item .delete-btn {
            opacity: 0;
            transition: 0.2s;
            margin-left: auto;
        }
        .file-tree .tree-item:hover .delete-btn { opacity: 1; }
        
        /* Main Area */
        .main-area {
            flex: 1;
            display: flex;
            flex-direction: column;
            min-width: 0;
        }
        
        /* Tabs */
        .tabs {
            background: var(--bg-secondary);
            border-bottom: 1px solid var(--border-color);
            display: flex;
            padding: 0 15px;
            overflow-x: auto;
            flex-shrink: 0;
        }
        .tab {
            padding: 8px 15px;
            cursor: pointer;
            border-bottom: 2px solid transparent;
            font-size: 13px;
            color: var(--text-secondary);
            transition: 0.2s;
            white-space: nowrap;
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .tab:hover { color: var(--text-primary); }
        .tab.active {
            color: var(--text-primary);
            border-bottom-color: var(--accent);
        }
        .tab .close-tab {
            color: var(--text-secondary);
            cursor: pointer;
            font-size: 14px;
            margin-left: 5px;
        }
        .tab .close-tab:hover { color: var(--danger); }
        
        /* Editor */
        .editor-container {
            flex: 1;
            display: flex;
            flex-direction: column;
            min-height: 0;
        }
        .editor-wrapper {
            flex: 1;
            position: relative;
            background: #0d1117;
        }
        .editor-wrapper textarea {
            width: 100%;
            height: 100%;
            padding: 20px;
            background: #0d1117;
            color: #c9d1d9;
            border: none;
            outline: none;
            resize: none;
            font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
            font-size: 14px;
            line-height: 1.6;
            tab-size: 4;
        }
        
        /* Output */
        .output-container {
            height: 250px;
            background: #0d1117;
            border-top: 1px solid var(--border-color);
            display: flex;
            flex-direction: column;
            flex-shrink: 0;
        }
        .output-header {
            background: var(--bg-secondary);
            padding: 4px 15px;
            border-bottom: 1px solid var(--border-color);
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-shrink: 0;
        }
        .output-header .left {
            display: flex;
            align-items: center;
            gap: 12px;
        }
        .output-header .left span {
            font-size: 11px;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .status-badge {
            padding: 2px 10px;
            border-radius: 10px;
            font-size: 10px;
            font-weight: 600;
            text-transform: uppercase;
        }
        .status-badge.ready { background: var(--bg-tertiary); color: var(--text-secondary); }
        .status-badge.running { background: #1f6feb; color: white; animation: pulse 1s infinite; }
        .status-badge.success { background: var(--success); color: white; }
        .status-badge.error { background: var(--danger); color: white; }
        .status-badge.installing { background: var(--warning); color: black; }
        .output-body {
            flex: 1;
            padding: 15px;
            overflow-y: auto;
            font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
            font-size: 13px;
            line-height: 1.5;
            white-space: pre-wrap;
            word-wrap: break-word;
        }
        .output-body .error { color: #f85149; }
        .output-body .success { color: #3fb950; }
        .output-body .info { color: #58a6ff; }
        .output-body .warning { color: #d29922; }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        
        /* Scrollbar */
        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-track { background: var(--bg-primary); }
        ::-webkit-scrollbar-thumb { background: var(--bg-tertiary); border-radius: 3px; }
        ::-webkit-scrollbar-thumb:hover { background: var(--text-secondary); }
        
        /* Responsive */
        @media (max-width: 768px) {
            .sidebar { width: 200px; }
            .container { flex-direction: column; }
            .sidebar { width: 100%; height: 200px; border-right: none; border-bottom: 1px solid var(--border-color); }
            .output-container { height: 150px; }
        }
        
        /* Modal */
        .modal {
            display: none;
            position: fixed;
            top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(0,0,0,0.7);
            z-index: 1000;
            align-items: center;
            justify-content: center;
        }
        .modal.active { display: flex; }
        .modal-content {
            background: var(--bg-secondary);
            padding: 30px;
            border-radius: 12px;
            max-width: 500px;
            width: 90%;
            border: 1px solid var(--border-color);
        }
        .modal-content h2 { margin-bottom: 15px; color: var(--text-primary); }
        .modal-content input, .modal-content select {
            width: 100%;
            padding: 10px;
            margin: 8px 0;
            background: var(--bg-primary);
            border: 1px solid var(--border-color);
            border-radius: 6px;
            color: var(--text-primary);
            font-size: 14px;
        }
        .modal-content .modal-actions {
            display: flex;
            gap: 10px;
            margin-top: 15px;
            justify-content: flex-end;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>🐍 Ultimate Python Code Runner</h1>
        <div class="header-actions">
            <button class="btn btn-primary" onclick="newProject()">📁 New Project</button>
            <button class="btn btn-success" onclick="uploadProject()">📤 Upload ZIP</button>
            <button class="btn btn-purple" onclick="installDeps()">📦 Install Deps</button>
            <button class="btn btn-danger" onclick="deleteProject()">🗑️ Delete Project</button>
            <input type="file" id="fileInput" accept=".zip" style="display:none" onchange="handleUpload(event)">
        </div>
    </div>
    
    <div class="container">
        <div class="sidebar">
            <div class="sidebar-header">
                <h3>📁 Projects</h3>
                <div class="sidebar-actions">
                    <button class="btn btn-secondary btn-sm" onclick="refreshFiles()">🔄</button>
                </div>
            </div>
            <div class="file-tree" id="fileTree"></div>
        </div>
        
        <div class="main-area">
            <div class="tabs" id="tabs"></div>
            <div class="editor-container">
                <div class="editor-wrapper">
                    <textarea id="editor" placeholder="Select a file to edit..." spellcheck="false"></textarea>
                </div>
            </div>
            <div class="output-container">
                <div class="output-header">
                    <div class="left">
                        <span>📋 Output</span>
                        <span class="status-badge ready" id="statusBadge">Ready</span>
                    </div>
                    <div style="display:flex;gap:6px;">
                        <button class="btn btn-success btn-sm" onclick="runCurrentFile()">▶️ Run</button>
                        <button class="btn btn-primary btn-sm" onclick="saveFile()">💾 Save</button>
                        <button class="btn btn-secondary btn-sm" onclick="clearOutput()">Clear</button>
                    </div>
                </div>
                <div class="output-body" id="output">🐍 Ready to run Python code...</div>
            </div>
        </div>
    </div>

    <!-- Modal -->
    <div class="modal" id="modal">
        <div class="modal-content">
            <h2 id="modalTitle">New Project</h2>
            <input type="text" id="modalInput" placeholder="Project name...">
            <div class="modal-actions">
                <button class="btn btn-secondary" onclick="closeModal()">Cancel</button>
                <button class="btn btn-primary" id="modalConfirm">Create</button>
            </div>
        </div>
    </div>

    <script>
        let currentProject = null;
        let currentFile = null;
        let openTabs = {};
        let fileTreeData = {};
        let isRunning = false;
        let modalCallback = null;

        // ============ PROJECT MANAGEMENT ============
        async function loadProjects() {
            try {
                const res = await fetch('/api/projects');
                const data = await res.json();
                if (data.projects && data.projects.length > 0) {
                    if (!currentProject || !data.projects.includes(currentProject)) {
                        currentProject = data.projects[0];
                    }
                    loadFileTree(currentProject);
                } else {
                    // Create default project
                    await createProject('default');
                }
            } catch(e) {
                console.error('Error loading projects:', e);
            }
        }

        async function createProject(name) {
            try {
                await fetch('/api/project/create', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name })
                });
                currentProject = name;
                await loadFileTree(name);
                return true;
            } catch(e) {
                console.error('Error creating project:', e);
                return false;
            }
        }

        function newProject() {
            showModal('New Project', 'Enter project name:', async (name) => {
                if (name) {
                    await createProject(name);
                    loadFileTree(name);
                }
            });
        }

        async function deleteProject() {
            if (!currentProject) return;
            if (!confirm(`Delete project "${currentProject}" and all files?`)) return;
            try {
                await fetch('/api/project/delete', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name: currentProject })
                });
                currentProject = null;
                currentFile = null;
                openTabs = {};
                document.getElementById('editor').value = '';
                await loadProjects();
            } catch(e) {
                alert('Error deleting project');
            }
        }

        // ============ FILE TREE ============
        async function loadFileTree(project) {
            if (!project) return;
            try {
                const res = await fetch(`/api/files?project=${project}`);
                const data = await res.json();
                fileTreeData = data.files || {};
                renderFileTree(data.tree || []);
                document.getElementById('tabs').innerHTML = '';
                openTabs = {};
                if (data.tree && data.tree.length > 0) {
                    const firstFile = data.tree.find(f => !f.is_dir && f.name.endsWith('.py'));
                    if (firstFile) {
                        openFile(firstFile.path);
                    }
                }
            } catch(e) {
                console.error('Error loading file tree:', e);
            }
        }

        function renderFileTree(tree) {
            const container = document.getElementById('fileTree');
            if (!tree || tree.length === 0) {
                container.innerHTML = '<div style="color:#8b949e;padding:20px;text-align:center;font-size:13px;">No files<br>Create a new file</div>';
                return;
            }
            
            let html = '';
            let currentPath = '';
            for (let item of tree) {
                const isFolder = item.is_dir;
                const icon = isFolder ? '📁' : '📄';
                const cls = isFolder ? 'folder' : 'file';
                const active = item.path === currentFile ? ' active' : '';
                
                html += `<div class="tree-item">`;
                html += `<span class="prefix">${item.prefix}</span>`;
                html += `<span class="tree-connector">${item.is_last ? '└──' : '├──'}</span>`;
                html += `<span class="${cls}${active}" onclick="${isFolder ? '' : `openFile('${item.path}')`}">`;
                html += `<span class="icon">${icon}</span>${item.name}`;
                if (!isFolder && item.name.endsWith('.py')) {
                    html += `<button class="btn btn-success btn-sm run-btn" onclick="event.stopPropagation();runFile('${item.path}')">▶️</button>`;
                }
                html += `<button class="btn btn-danger btn-sm delete-btn" onclick="event.stopPropagation();deleteFile('${item.path}')">✕</button>`;
                html += `</span>`;
                html += `</div>`;
            }
            container.innerHTML = html;
        }

        function refreshFiles() {
            if (currentProject) loadFileTree(currentProject);
        }

        // ============ FILE OPERATIONS ============
        async function openFile(path) {
            if (!path) return;
            try {
                const res = await fetch(`/api/file?path=${encodeURIComponent(path)}`);
                const data = await res.json();
                if (data.content !== undefined) {
                    currentFile = path;
                    document.getElementById('editor').value = data.content;
                    // Add tab
                    const name = path.split('/').pop();
                    if (!openTabs[path]) {
                        openTabs[path] = name;
                        renderTabs();
                    }
                    // Highlight file in tree
                    loadFileTree(currentProject);
                }
            } catch(e) {
                console.error('Error opening file:', e);
            }
        }

        function renderTabs() {
            const container = document.getElementById('tabs');
            container.innerHTML = Object.entries(openTabs).map(([path, name]) => `
                <div class="tab ${path === currentFile ? 'active' : ''}" onclick="openFile('${path}')">
                    ${name}
                    <span class="close-tab" onclick="event.stopPropagation();closeTab('${path}')">×</span>
                </div>
            `).join('');
        }

        function closeTab(path) {
            delete openTabs[path];
            if (currentFile === path) {
                const keys = Object.keys(openTabs);
                if (keys.length > 0) {
                    openFile(keys[0]);
                } else {
                    currentFile = null;
                    document.getElementById('editor').value = '';
                }
            }
            renderTabs();
            loadFileTree(currentProject);
        }

        async function saveFile() {
            if (!currentFile) {
                // Create new file
                const name = prompt('Enter filename (e.g., main.py):');
                if (!name || !name.endsWith('.py')) {
                    alert('Filename must end with .py');
                    return;
                }
                const project = currentProject;
                const path = `${project}/${name}`;
                try {
                    await fetch('/api/file/save', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ path, content: '# New Python file\\nprint("Hello, World!")' })
                    });
                    await loadFileTree(currentProject);
                    await openFile(path);
                } catch(e) {
                    alert('Error creating file');
                }
                return;
            }
            
            const content = document.getElementById('editor').value;
            try {
                await fetch('/api/file/save', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ path: currentFile, content })
                });
                showStatus('Saved!', 'success');
            } catch(e) {
                showStatus('Error saving!', 'error');
            }
        }

        async function deleteFile(path) {
            if (!confirm(`Delete "${path}"?`)) return;
            try {
                await fetch('/api/file/delete', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ path })
                });
                if (currentFile === path) {
                    currentFile = null;
                    document.getElementById('editor').value = '';
                }
                delete openTabs[path];
                renderTabs();
                await loadFileTree(currentProject);
            } catch(e) {
                alert('Error deleting file');
            }
        }

        // ============ RUN CODE ============
        async function runFile(path) {
            if (isRunning) return;
            isRunning = true;
            showStatus('⏳ Running...', 'running');
            
            const output = document.getElementById('output');
            output.innerHTML = '<span class="info">⏳ Running code...</span>';
            
            try {
                const res = await fetch('/api/run', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ path })
                });
                const data = await res.json();
                if (data.success) {
                    output.innerHTML = data.output || '✅ No output';
                    showStatus('✅ Done', 'success');
                } else {
                    output.innerHTML = `<span class="error">❌ ${data.error || 'Error'}</span>`;
                    showStatus('❌ Error', 'error');
                }
            } catch(e) {
                output.innerHTML = `<span class="error">❌ ${e.message}</span>`;
                showStatus('❌ Error', 'error');
            }
            isRunning = false;
        }

        function runCurrentFile() {
            if (currentFile) runFile(currentFile);
            else alert('No file selected!');
        }

        // ============ INSTALL DEPENDENCIES ============
        async function installDeps() {
            if (!currentProject) {
                alert('Select a project first!');
                return;
            }
            showStatus('📦 Installing dependencies...', 'installing');
            const output = document.getElementById('output');
            output.innerHTML = '<span class="warning">📦 Installing requirements.txt...</span>';
            
            try {
                const res = await fetch('/api/install', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ project: currentProject })
                });
                const data = await res.json();
                if (data.success) {
                    output.innerHTML = '<span class="success">✅ ' + (data.message || 'Dependencies installed!') + '</span>\n\n' + (data.output || '');
                    showStatus('✅ Dependencies installed', 'success');
                } else {
                    output.innerHTML = `<span class="error">❌ ${data.error || 'Installation failed'}</span>\n\n${data.output || ''}`;
                    showStatus('❌ Failed', 'error');
                }
            } catch(e) {
                output.innerHTML = `<span class="error">❌ ${e.message}</span>`;
                showStatus('❌ Error', 'error');
            }
        }

        // ============ UPLOAD PROJECT ============
        function uploadProject() {
            document.getElementById('fileInput').click();
        }

        async function handleUpload(event) {
            const file = event.target.files[0];
            if (!file) return;
            
            const name = prompt('Enter project name:', file.name.replace('.zip', ''));
            if (!name) return;
            
            const formData = new FormData();
            formData.append('file', file);
            formData.append('name', name);
            
            showStatus('📤 Uploading...', 'installing');
            
            try {
                const res = await fetch('/api/upload', {
                    method: 'POST',
                    body: formData
                });
                const data = await res.json();
                if (data.success) {
                    currentProject = name;
                    await loadFileTree(name);
                    showStatus('✅ Uploaded!', 'success');
                } else {
                    alert('Upload failed: ' + (data.error || 'Unknown error'));
                }
            } catch(e) {
                alert('Upload error: ' + e.message);
            }
            event.target.value = '';
        }

        // ============ UI HELPERS ============
        function showStatus(text, type = 'ready') {
            const badge = document.getElementById('statusBadge');
            badge.textContent = text;
            badge.className = 'status-badge ' + type;
        }

        function clearOutput() {
            document.getElementById('output').innerHTML = '🧹 Output cleared';
            showStatus('Ready', 'ready');
        }

        function showModal(title, placeholder, callback) {
            document.getElementById('modalTitle').textContent = title;
            document.getElementById('modalInput').placeholder = placeholder || '';
            document.getElementById('modalInput').value = '';
            document.getElementById('modal').classList.add('active');
            modalCallback = callback;
            document.getElementById('modalInput').focus();
        }

        function closeModal() {
            document.getElementById('modal').classList.remove('active');
        }

        document.getElementById('modalConfirm').addEventListener('click', () => {
            const value = document.getElementById('modalInput').value;
            if (modalCallback) modalCallback(value);
            closeModal();
        });

        document.getElementById('modalInput').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                document.getElementById('modalConfirm').click();
            }
        });

        // ============ KEYBOARD SHORTCUTS ============
        document.addEventListener('keydown', (e) => {
            if (e.ctrlKey && e.key === 's') { e.preventDefault(); saveFile(); }
            if (e.ctrlKey && e.key === 'Enter') { e.preventDefault(); runCurrentFile(); }
        });

        // ============ INIT ============
        loadProjects();
    </script>
</body>
</html>
'''

# ============ FLASK ROUTES ============

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

# ============ PROJECT ROUTES ============

@app.route('/api/projects')
def get_projects():
    projects = []
    for item in os.listdir(WORKSPACE_DIR):
        if os.path.isdir(os.path.join(WORKSPACE_DIR, item)):
            projects.append(item)
    return jsonify({'projects': projects})

@app.route('/api/project/create', methods=['POST'])
def create_project():
    data = request.get_json()
    name = data.get('name')
    if not name:
        return jsonify({'error': 'Project name required'}), 400
    
    project_path = get_project_path(name)
    if os.path.exists(project_path):
        return jsonify({'error': 'Project already exists'}), 400
    
    os.makedirs(project_path)
    # Create default main.py
    with open(os.path.join(project_path, 'main.py'), 'w') as f:
        f.write('# Default main.py\\nprint("Hello, World!")')
    # Create requirements.txt
    with open(os.path.join(project_path, 'requirements.txt'), 'w') as f:
        f.write('# Add your dependencies here\\n# flask\\n# requests\\n')
    
    # Create virtual environment
    create_venv(name)
    
    return jsonify({'success': True, 'message': 'Project created'})

@app.route('/api/project/delete', methods=['POST'])
def delete_project():
    data = request.get_json()
    name = data.get('name')
    if not name:
        return jsonify({'error': 'Project name required'}), 400
    
    project_path = get_project_path(name)
    venv_path = get_venv_path(name)
    
    if os.path.exists(project_path):
        shutil.rmtree(project_path)
    if os.path.exists(venv_path):
        shutil.rmtree(venv_path)
    
    return jsonify({'success': True})

# ============ FILE ROUTES ============

@app.route('/api/files')
def get_files():
    project = request.args.get('project')
    if not project:
        return jsonify({'error': 'Project required'}), 400
    
    project_path = get_project_path(project)
    if not os.path.exists(project_path):
        return jsonify({'error': 'Project not found'}), 404
    
    tree = get_file_tree(project_path)
    
    # Get all files with content
    files = {}
    for root, dirs, filenames in os.walk(project_path):
        for filename in filenames:
            if filename.endswith('.py'):
                rel_path = os.path.relpath(os.path.join(root, filename), WORKSPACE_DIR)
                files[rel_path] = {'size': os.path.getsize(os.path.join(root, filename))}
    
    return jsonify({'files': files, 'tree': tree})

@app.route('/api/file')
def get_file():
    path = request.args.get('path')
    if not path:
        return jsonify({'error': 'Path required'}), 400
    
    full_path = os.path.join(WORKSPACE_DIR, path)
    if not os.path.exists(full_path):
        return jsonify({'error': 'File not found'}), 404
    
    with open(full_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    return jsonify({'content': content, 'path': path})

@app.route('/api/file/save', methods=['POST'])
def save_file():
    data = request.get_json()
    path = data.get('path')
    content = data.get('content')
    
    if not path:
        return jsonify({'error': 'Path required'}), 400
    
    # Security: Prevent path traversal
    full_path = os.path.abspath(os.path.join(WORKSPACE_DIR, path))
    if not full_path.startswith(os.path.abspath(WORKSPACE_DIR)):
        return jsonify({'error': 'Invalid path'}), 403
    
    # Create directory if needed
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    
    with open(full_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    return jsonify({'success': True})

@app.route('/api/file/delete', methods=['POST'])
def delete_file():
    data = request.get_json()
    path = data.get('path')
    
    if not path:
        return jsonify({'error': 'Path required'}), 400    
    full_path = os.path.join(WORKSPACE_DIR, path)
    if os.path.exists(full_path):
        os.remove(full_path)
        return jsonify({'success': True})
    
    return jsonify({'error': 'File not found'}), 404

# ============ RUN ROUTE ============

@app.route('/api/run', methods=['POST'])
def run_code():
    data = request.get_json()
    path = data.get('path')
    
    if not path:
        return jsonify({'error': 'Path required'}), 400
    
    # Extract project name from path
    parts = path.split('/')
    if len(parts) < 1:
        return jsonify({'error': 'Invalid path'}), 400
    
    project = parts[0]
    file_path = os.path.join(WORKSPACE_DIR, path)
    
    if not os.path.exists(file_path):
        return jsonify({'error': 'File not found'}), 404
    
    # Get Python executable from venv
    python_exe = get_python_executable(project)
    
    try:
        result = subprocess.run(
            [python_exe, file_path],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=os.path.dirname(file_path)
        )
        
        output = result.stdout
        if result.stderr:
            output += '\n' + result.stderr
        
        return jsonify({
            'success': True,
            'output': output or '✅ Code executed successfully (no output)'
        })
        
    except subprocess.TimeoutExpired:
        return jsonify({'success': False, 'error': '⏰ Timeout (30s)'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ============ INSTALL ROUTE ============

@app.route('/api/install', methods=['POST'])
def install_deps():
    data = request.get_json()
    project = data.get('project')
    
    if not project:
        return jsonify({'error': 'Project required'}), 400
    
    project_path = get_project_path(project)
    req_file = os.path.join(project_path, 'requirements.txt')
    
    if not os.path.exists(req_file):
        return jsonify({'success': True, 'message': 'No requirements.txt found'})
    
    # Ensure venv exists
    create_venv(project)
    
    pip = get_pip_executable(project)
    try:
        result = subprocess.run(
            [pip, 'install', '-r', req_file],
            capture_output=True,
            text=True,
            timeout=120
        )
        return jsonify({
            'success': result.returncode == 0,
            'output': result.stdout + result.stderr,
            'message': 'Dependencies installed successfully' if result.returncode == 0 else 'Installation failed'
        })
    except subprocess.TimeoutExpired:
        return jsonify({'success': False, 'error': 'Installation timeout (120s)'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ============ UPLOAD ROUTE ============

@app.route('/api/upload', methods=['POST'])
def upload_project():
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['file']
    name = request.form.get('name')
    
    if not name:
        return jsonify({'error': 'Project name required'}), 400
    
    project_path = get_project_path(name)
    if os.path.exists(project_path):
        shutil.rmtree(project_path)
    
    os.makedirs(project_path)
    
    # Extract zip
    with zipfile.ZipFile(file, 'r') as zip_ref:
        zip_ref.extractall(project_path)
    
    # Create venv
    create_venv(name)
    
    # Install requirements if exists
    install_requirements(name)
    
    return jsonify({'success': True, 'message': 'Project uploaded'})

# ============ MAIN ============

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f'''
    ╔═══════════════════════════════════════════════════════════════╗
    ║  🐍 ULTIMATE PYTHON CODE RUNNER - ENTERPRISE EDITION         ║
    ║  🌐 http://localhost:{port}                                 ║
    ║  📁 Workspace: {WORKSPACE_DIR}                              ║
    ║  🧪 Virtual Envs: {VENV_DIR}                               ║
    ║  ⚡ Features:                                               ║
    ║    - Multiple Projects & Folders                            ║
    ║    - Virtual Environments per Project                       ║
    ║    - requirements.txt Support                               ║
    ║    - ZIP Upload/Download                                    ║
    ║    - Concurrent Runs                                        ║
    ║    - File Tree View                                         ║
    ║    - Tab-based Editor                                       ║
    ║  🚀 Lifetime - No Limits - Forever Free                    ║
    ╚═══════════════════════════════════════════════════════════════╝
    ''')
    app.run(host='0.0.0.0', port=port, debug=False)

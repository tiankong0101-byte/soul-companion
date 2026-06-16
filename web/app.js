/**
 * Soul Companion v4.0 — 前端应用
 * 菲菲的聊天界面
 */

// ===== 初始化 =====
const socket = io();
const chatMessages = document.getElementById('chat-messages');
const userInput = document.getElementById('user-input');
const btnSend = document.getElementById('btn-send');
const btnVoice = document.getElementById('btn-voice');
const btnImage = document.getElementById('btn-image');
const imageInput = document.getElementById('image-input');
const btnClear = document.getElementById('btn-clear');
const btnStats = document.getElementById('btn-stats');
const charCount = document.getElementById('char-count');
const emotionIndicator = document.getElementById('emotion-indicator');
const emotionText = document.getElementById('emotion-text');
const statusBadge = document.getElementById('status-badge');
const statsModal = document.getElementById('stats-modal');
const statsBody = document.getElementById('stats-body');
const btnCloseStats = document.getElementById('btn-close-stats');

let isGenerating = false;
let isRecording = false;

// ===== 情感映射 =====
const emotionMap = {
    happy: { emoji: '😊', label: '开心', color: '#4CAF50' },
    sad: { emoji: '😢', label: '难过', color: '#2196F3' },
    angry: { emoji: '😠', label: '生气', color: '#f44336' },
    surprised: { emoji: '😲', label: '惊讶', color: '#FF9800' },
    neutral: { emoji: '😐', label: '平静', color: '#9E9E9E' },
    love: { emoji: '🥰', label: '爱你', color: '#E91E63' },
    shy: { emoji: '😳', label: '害羞', color: '#9C27B0' },
    gentle: { emoji: '😌', label: '温柔', color: '#00BCD4' },
};

// ===== WebSocket 事件 =====
socket.on('connect', () => {
    statusBadge.textContent = '在线';
    statusBadge.style.background = '#4CAF50';
    console.log('已连接到服务器');
});

socket.on('disconnect', () => {
    statusBadge.textContent = '离线';
    statusBadge.style.background = '#f44336';
    console.log('与服务器断开连接');
});

socket.on('chat_response', (data) => {
    isGenerating = false;
    btnSend.disabled = false;

    if (data.error) {
        addMessage('system', `⚠️ ${data.error}`);
        return;
    }

    // 添加助手消息
    addMessage('assistant', data.response, data.emotion, data.mode);

    // 如果有图片，在消息后追加图片
    if (data.image_path) {
        addImageMessage(data.image_path);
    }

    // 如果有提醒列表
    if (data.reminders) {
        addRemindersMessage(data.reminders);
    }

    // 更新情感指示器
    updateEmotion(data.emotion);

    // Live2D 事件
    if (data.live2d_event) {
        handleLive2DEvent(data.live2d_event);
    }
});

// 日程到期提醒
socket.on('reminder_alert', (data) => {
    addMessage('system', `⏰ 提醒：${data.message}`);
    // 尝试播放提示音
    try {
        const audio = new Audio('data:audio/wav;base64,UklGRnoGAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQ==');
        audio.play().catch(() => {});
    } catch (e) {}
});

// ===== 消息处理 =====
function addMessage(role, content, emotion = null, mode = null) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role}`;

    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';
    bubble.textContent = content;

    if (role === 'assistant' && emotion) {
        const emotionInfo = emotionMap[emotion] || emotionMap.neutral;
        bubble.setAttribute('data-emotion', emotion);
    }

    messageDiv.appendChild(bubble);

    // 时间戳
    const time = document.createElement('div');
    time.className = 'message-time';
    time.textContent = new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
    messageDiv.appendChild(time);

    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function addTypingIndicator() {
    const typingDiv = document.createElement('div');
    typingDiv.className = 'message assistant typing-message';
    typingDiv.id = 'typing-indicator';

    const bubble = document.createElement('div');
    bubble.className = 'message-bubble typing';
    bubble.innerHTML = '<span class="dot"></span><span class="dot"></span><span class="dot"></span>';

    typingDiv.appendChild(bubble);
    chatMessages.appendChild(typingDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function addImageMessage(imagePath) {
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message assistant';

    const img = document.createElement('img');
    img.className = 'message-image';
    img.src = `/static/images/${imagePath.split('/').pop()}`;
    img.alt = '菲菲生成的图片';
    img.onerror = function() {
        // 如果本地路径不行，尝试数据目录
        this.src = `data/images/${imagePath.split('/').pop()}`;
    };

    messageDiv.appendChild(img);
    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function addRemindersMessage(reminders) {
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message assistant';

    const bubble = document.createElement('div');
    bubble.className = 'message-bubble reminders-bubble';

    let html = '<div class="reminders-title">📋 你的提醒：</div>';
    if (reminders.length === 0) {
        html += '<div class="reminder-empty">目前没有待处理的提醒~</div>';
    } else {
        reminders.forEach(r => {
            const timeStr = new Date(r.remind_at).toLocaleString('zh-CN');
            html += `<div class="reminder-item">
                <span class="reminder-time">⏰ ${timeStr}</span>
                <span class="reminder-title">${r.title}</span>
            </div>`;
        });
    }

    bubble.innerHTML = html;
    messageDiv.appendChild(bubble);
    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function removeTypingIndicator() {
    const typing = document.getElementById('typing-indicator');
    if (typing) typing.remove();
}

function sendMessage() {
    const text = userInput.value.trim();
    if (!text || isGenerating) return;

    isGenerating = true;
    btnSend.disabled = true;

    addMessage('user', text);
    addTypingIndicator();

    socket.emit('chat_message', { message: text });

    userInput.value = '';
    updateCharCount();
    autoResizeTextarea();
}

// ===== 情感更新 =====
function updateEmotion(emotion) {
    const info = emotionMap[emotion] || emotionMap.neutral;
    emotionText.textContent = `${info.emoji} ${info.label}`;
    emotionIndicator.style.background = info.color;
}

// ===== Live2D 事件处理 =====
function handleLive2DEvent(event) {
    // 通过 canvas 绘制 Live2D 动画占位
    const canvas = document.getElementById('live2d-canvas');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // 简单的表情绘制（占位）
    const emotion = event.emotion || 'neutral';
    const info = emotionMap[emotion] || emotionMap.neutral;

    ctx.font = '80px serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(info.emoji, canvas.width / 2, canvas.height / 2);
}

// ===== 语音输入 =====
async function toggleVoice() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        alert('您的浏览器不支持语音输入');
        return;
    }

    if (isRecording) {
        // 停止录音
        if (window.mediaRecorder) {
            window.mediaRecorder.stop();
        }
        isRecording = false;
        btnVoice.classList.remove('recording');
        return;
    }

    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        const mediaRecorder = new MediaRecorder(stream);
        const audioChunks = [];

        mediaRecorder.ondataavailable = (event) => {
            audioChunks.push(event.data);
        };

        mediaRecorder.onstop = async () => {
            stream.getTracks().forEach(track => track.stop());

            const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
            // TODO: 发送到 ASR 后端
            console.log('录音完成，大小:', audioBlob.size, 'bytes');
        };

        mediaRecorder.start();
        window.mediaRecorder = mediaRecorder;
        isRecording = true;
        btnVoice.classList.add('recording');

        // 30秒自动停止
        setTimeout(() => {
            if (isRecording) toggleVoice();
        }, 30000);
    } catch (err) {
        console.error('麦克风访问失败:', err);
        alert('无法访问麦克风，请检查权限设置');
    }
}

// ===== UI 辅助 =====
function updateCharCount() {
    charCount.textContent = userInput.value.length;
}

function autoResizeTextarea() {
    userInput.style.height = 'auto';
    userInput.style.height = Math.min(userInput.scrollHeight, 120) + 'px';
}

function clearChat() {
    chatMessages.innerHTML = '<div class="welcome-message"><p>对话已清空~ 重新开始吧 💕</p></div>';
    socket.emit('chat_clear');
}

async function showStats() {
    try {
        const res = await fetch('/api/stats');
        const data = await res.json();
        statsBody.innerHTML = `
            <div class="stats-grid">
                <div class="stat-item">
                    <div class="stat-value">${data.total_messages || 0}</div>
                    <div class="stat-label">总消息数</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value">${data.user_messages || 0}</div>
                    <div class="stat-label">天哥的消息</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value">${data.assistant_messages || 0}</div>
                    <div class="stat-label">菲菲的消息</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value">${data.memory_enabled ? '✅' : '❌'}</div>
                    <div class="stat-label">记忆系统</div>
                </div>
            </div>
            <div class="stat-session">会话ID: ${data.session_id || 'N/A'}</div>
        `;
        statsModal.style.display = 'flex';
    } catch (err) {
        console.error('获取统计失败:', err);
    }
}

// ===== 图片识图 =====
function triggerImageUpload() {
    imageInput.click();
}

async function handleImageUpload(e) {
    const file = e.target.files[0];
    if (!file) return;

    // 检查文件类型
    if (!file.type.startsWith('image/')) {
        alert('请选择图片文件');
        return;
    }

    // 显示用户发送的图片预览
    const reader = new FileReader();
    reader.onload = async function(ev) {
        const imagePreviewDiv = document.createElement('div');
        imagePreviewDiv.className = 'message user';
        const img = document.createElement('img');
        img.className = 'message-image';
        img.src = ev.target.result;
        imagePreviewDiv.appendChild(img);
        chatMessages.appendChild(imagePreviewDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;

        // 添加打字指示器
        addTypingIndicator();

        // 转为 base64 发送
        const base64 = ev.target.result;

        // 通过 WebSocket 发送
        socket.emit('analyze_image', {
            image_base64: base64,
            prompt: '请仔细观察这张图片，然后用温暖自然的语气描述你看到了什么~',
        });
    };
    reader.readAsDataURL(file);

    // 清空 input 以便重复上传同一张图
    imageInput.value = '';
}

// 识图结果
socket.on('vision_response', (data) => {
    removeTypingIndicator();

    if (data.error) {
        addMessage('system', `⚠️ 识图失败: ${data.error}`);
        return;
    }

    addMessage('assistant', data.response, 'happy', 'default');
    updateEmotion('happy');
});

// 识图状态
socket.on('vision_status', (data) => {
    if (data.status === 'analyzing') {
        addTypingIndicator();
    }
});

// ===== 事件绑定 =====
btnSend.addEventListener('click', sendMessage);
btnVoice.addEventListener('click', toggleVoice);
btnImage.addEventListener('click', triggerImageUpload);
imageInput.addEventListener('change', handleImageUpload);
btnClear.addEventListener('click', clearChat);
btnStats.addEventListener('click', showStats);
btnCloseStats.addEventListener('click', () => { statsModal.style.display = 'none'; });

userInput.addEventListener('input', () => {
    updateCharCount();
    autoResizeTextarea();
});

userInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

// 初始化
updateCharCount();
handleLive2DEvent({ emotion: 'neutral', mode: 'default' });

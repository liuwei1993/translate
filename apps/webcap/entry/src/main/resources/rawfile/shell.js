(function () {
  if (window.__capShell) {
    return;
  }
  var bridge = window.harmonyShell;
  if (!bridge || !bridge.start || !bridge.stop) {
    return;
  }
  window.__capShell = true;
  var socket = null;
  var connecting = null;
  var opening = false;
  var stopping = false;
  var live = { source: '', translation: '' };
  var history = [];

  function show(name) {
    ['ready', 'listening', 'mic', 'down'].forEach(function (key) {
      var panel = document.getElementById('panel-' + key);
      if (panel) {
        panel.hidden = key !== name;
      }
    });
    var status = document.getElementById('status');
    var labels = {
      ready: '准备',
      listening: '正在听',
      mic: '麦克风不可用',
      down: '连接中断'
    };
    if (status) {
      status.textContent = labels[name] || '';
    }
    var historyPanel = document.getElementById('panel-history');
    if (historyPanel) {
      historyPanel.hidden = true;
    }
  }

  function render() {
    var source = document.getElementById('live-source');
    var translation = document.getElementById('live-translation');
    if (source) {
      source.textContent = live.source;
    }
    if (translation) {
      translation.textContent = live.translation;
    }
    ['history', 'down-history'].forEach(function (id) {
      var list = document.getElementById(id);
      if (!list) {
        return;
      }
      list.textContent = '';
      history.forEach(function (item) {
        var row = document.createElement('li');
        row.className = item.kind;
        if (typeof window.renderHistoryRow === 'function') {
          window.renderHistoryRow(row, item);
        }
        list.appendChild(row);
      });
    });
  }

  function push(kind, note) {
    if (!live.source && !live.translation && kind === 'ok') {
      live = { source: '', translation: '' };
      render();
      return;
    }
    var item = { source: live.source, translation: live.translation, kind: kind };
    if (note) {
      item.note = note;
    }
    history.unshift(item);
    live = { source: '', translation: '' };
    render();
  }

  function stopPlayback() {
    if (typeof window.stopSpeaking === 'function') {
      window.stopSpeaking();
    }
  }

  window.onHarmonyPcm = function (b64) {
    if (!b64 || !socket || socket.readyState !== 1) {
      return;
    }
    var binary = atob(b64);
    var bytes = new Uint8Array(binary.length);
    for (var i = 0; i < binary.length; i++) {
      bytes[i] = binary.charCodeAt(i);
    }
    socket.send(bytes.buffer);
  };

  window.onHarmonyMicDenied = function () {
    show('mic');
  };

  function startMessage() {
    var selected = document.querySelector('#direction-menu button[aria-checked="true"]');
    var mode = selected ? selected.getAttribute('data-mode') : 'auto';
    if (!mode || mode === 'auto') {
      return { type: 'start' };
    }
    return { type: 'start', target: mode };
  }

  function closeActiveSocket() {
    var current = socket || connecting;
    socket = null;
    connecting = null;
    if (!current) {
      return;
    }
    if (current.readyState === 1) {
      try {
        current.send(JSON.stringify({ type: 'stop' }));
      } catch (error) {
      }
    }
    try {
      current.close();
    } catch (error) {
    }
  }

  function stopAll() {
    stopPlayback();
    stopping = true;
    opening = false;
    try {
      bridge.stop();
    } catch (error) {
    }
    closeActiveSocket();
    live = { source: '', translation: '' };
    render();
    show('ready');
  }

  function attach(ws) {
    ws.addEventListener('message', function (event) {
      if (stopping || socket !== ws) {
        return;
      }
      var payload;
      try {
        payload = JSON.parse(event.data);
      } catch (error) {
        return;
      }
      if (payload.type === 'source') {
        live.source = payload.text || '';
      }
      if (payload.type === 'translation') {
        live.translation = payload.text || '';
      }
      render();
      if (payload.type === 'translation' && payload.final) {
        push('ok');
      }
      if (payload.type !== 'error') {
        return;
      }
      if (payload.code === 'auth' || payload.message === '连不上服务器') {
        var notice = document.getElementById('ready-error');
        if (notice) {
          notice.hidden = false;
          notice.textContent = payload.message;
        }
        stopAll();
        return;
      }
      if (payload.message === '连接中断') {
        if (live.source || live.translation) {
          push('partial');
        }
        stopping = true;
        try {
          bridge.stop();
        } catch (error) {
        }
        socket = null;
        show('down');
        return;
      }
      push('failed', payload.message || '');
    });
    ws.addEventListener('close', function () {
      if (stopping) {
        return;
      }
      if (live.source || live.translation) {
        push('partial');
      }
      try {
        bridge.stop();
      } catch (error) {
      }
      socket = null;
      show('down');
    });
  }

  function begin() {
    if (opening) {
      return;
    }
    opening = true;
    stopping = false;
    if (socket) {
      socket.close();
      socket = null;
    }
    var protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    var ws = new WebSocket(protocol + '//' + location.host + '/ws');
    ws.binaryType = 'arraybuffer';
    connecting = ws;
    ws.addEventListener('open', function () {
      opening = false;
      if (stopping || connecting !== ws) {
        try {
          ws.close();
        } catch (error) {
        }
        return;
      }
      connecting = null;
      socket = ws;
      attach(ws);
      ws.send(JSON.stringify(startMessage()));
      bridge.start();
      show('listening');
    }, { once: true });
    ws.addEventListener('error', function () {
      opening = false;
      if (connecting === ws) {
        connecting = null;
      }
      if (stopping) {
        return;
      }
      var notice = document.getElementById('ready-error');
      if (notice) {
        notice.hidden = false;
        notice.textContent = '连不上服务器';
      }
      show('ready');
    }, { once: true });
  }

  function collectLines() {
    var lines = [];
    for (var i = history.length - 1; i >= 0; i--) {
      var item = history[i];
      if (!(item.source || item.translation)) {
        continue;
      }
      lines.push({
        source: item.source || '',
        translation: item.translation || '',
        kind: item.kind || 'ok'
      });
    }
    if (live.source || live.translation) {
      lines.push({
        source: live.source || '',
        translation: live.translation || '',
        kind: 'partial'
      });
    }
    return lines;
  }

  function newSession() {
    stopPlayback();
    var active = opening || connecting || (socket && (socket.readyState === 0 || socket.readyState === 1));
    if (active) {
      stopping = true;
      opening = false;
      try {
        bridge.stop();
      } catch (error) {
      }
      closeActiveSocket();
    }
    var lines = collectLines();
    var label = document.getElementById('direction-label');
    var direction = label ? label.textContent : '';
    var failed = false;
    try {
      if (typeof window.univoiceSaveSession !== 'function') {
        throw new Error('missing save');
      }
      window.univoiceSaveSession(lines, direction);
    } catch (error) {
      failed = lines.length > 0;
    }
    var notice = document.getElementById('ready-error');
    if (failed) {
      if (notice) {
        notice.hidden = false;
        notice.textContent = '这次没能保存到本机';
      }
      show('ready');
      return;
    }
    if (notice) {
      notice.hidden = true;
    }
    history = [];
    live = { source: '', translation: '' };
    render();
    show('ready');
  }

  function rebind(id, handler) {
    var el = document.getElementById(id);
    if (!el || !el.parentNode) {
      return;
    }
    var clone = el.cloneNode(true);
    el.parentNode.replaceChild(clone, el);
    clone.addEventListener('click', handler);
  }

  rebind('start', begin);
  rebind('retry-mic', begin);
  rebind('reconnect', begin);
  rebind('stop', stopAll);
  rebind('new-session-ready', newSession);
  rebind('new-session-listening', newSession);
  rebind('new-session-down', newSession);
  var menu = document.getElementById('direction-menu');
  if (menu) {
    menu.addEventListener('click', function () {
      setTimeout(function () {
        if (!socket || socket.readyState !== 1) {
          return;
        }
        live = { source: '', translation: '' };
        render();
        socket.send(JSON.stringify(startMessage()));
      }, 0);
    });
  }
})();

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
        if (item.kind === 'failed' || item.kind === 'partial') {
          var tag = document.createElement('span');
          tag.className = 'tag';
          tag.textContent = item.kind === 'failed' ? '这句失败' : '未完成';
          row.appendChild(tag);
        }
        var strong = document.createElement('strong');
        strong.textContent = item.source || '…';
        var span = document.createElement('span');
        span.textContent = item.translation || '';
        row.appendChild(strong);
        row.appendChild(span);
        list.appendChild(row);
      });
    });
  }

  function push(kind) {
    if (!live.source && !live.translation && kind === 'ok') {
      live = { source: '', translation: '' };
      render();
      return;
    }
    history.push({ source: live.source, translation: live.translation, kind: kind });
    live = { source: '', translation: '' };
    render();
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
    var button = document.querySelector('.choice.selected');
    if (!button) {
      return { type: 'start' };
    }
    return { type: 'start', target: button.getAttribute('data-target') || 'en' };
  }

  function markSelected(value) {
    document.querySelectorAll('.choice').forEach(function (button) {
      if (button.getAttribute('data-target') === value) {
        button.classList.add('selected');
      } else {
        button.classList.remove('selected');
      }
    });
  }

  function stopAll() {
    stopping = true;
    try {
      bridge.stop();
    } catch (error) {
    }
    if (socket && socket.readyState === 1) {
      socket.send(JSON.stringify({ type: 'stop' }));
      socket.close();
    }
    socket = null;
    live = { source: '', translation: '' };
    render();
    show('ready');
  }

  function attach(ws) {
    ws.addEventListener('message', function (event) {
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
      push('failed');
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
    ws.addEventListener('open', function () {
      opening = false;
      socket = ws;
      attach(ws);
      ws.send(JSON.stringify(startMessage()));
      bridge.start();
      show('listening');
    }, { once: true });
    ws.addEventListener('error', function () {
      opening = false;
      var notice = document.getElementById('ready-error');
      if (notice) {
        notice.hidden = false;
        notice.textContent = '连不上服务器';
      }
      show('ready');
    }, { once: true });
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
  document.querySelectorAll('.choice').forEach(function (button) {
    button.addEventListener('click', function () {
      var value = button.getAttribute('data-target');
      markSelected(value);
      if (socket && socket.readyState === 1 && button.closest('#panel-listening')) {
        live = { source: '', translation: '' };
        render();
        socket.send(JSON.stringify({ type: 'start', target: value }));
      }
    });
  });
})();

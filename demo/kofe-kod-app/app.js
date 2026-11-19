/* Приложение кофейни для Telegram (Mini App).
   Меню, корзина и оформление заказа. Заказ уходит боту через Telegram.WebApp.sendData — это работает, когда
   приложение открыто кнопкой под полем ввода в чате с ботом. Бот превращает заказ в обычное сообщение клиента
   и дальше работает как всегда: заявка по телефону -> таблица «Лиды» -> уведомление менеджеру.
   Всё содержимое (название, меню, цены, часы) берётся из data.json рядом — код менять не нужно. */
(() => {
  'use strict';

  const tg = window.Telegram && window.Telegram.WebApp;
  const inTelegram = !!(tg && tg.platform && tg.platform !== 'unknown');
  // Открыто кнопкой под полем ввода (а не кнопкой «Меню» или ссылкой) — только так заказ можно отправить боту.
  const canSend = inTelegram && !(tg.initDataUnsafe && tg.initDataUnsafe.query_id);
  const MAX_BYTES = 4096;                    // предел Telegram для sendData

  const state = { data: null, items: new Map(), cart: new Map(), screen: 'menu', mode: 'pickup',
                  form: { name: '', phone: '', address: '', time: '', comment: '' }, errors: {} };
  const shell = {};

  // ---------- помощники ----------
  function el(tag, props, ...children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(props || {})) {
      if (v === undefined || v === null || v === false) continue;
      if (k === 'class') node.className = v;
      else if (k === 'text') node.textContent = v;
      else if (k.startsWith('on')) node.addEventListener(k.slice(2), v);
      else node.setAttribute(k, v === true ? '' : v);
    }
    for (const c of children.flat()) if (c !== null && c !== undefined && c !== false) node.append(c);
    return node;
  }
  const money = n => new Intl.NumberFormat('ru-RU').format(n) + ' ' + (state.data.currency || '₽');
  const toMin = s => { const [h, m] = String(s || '0:0').split(':').map(Number); return (h || 0) * 60 + (m || 0); };
  const hhmm = m => String(Math.floor(m / 60) % 24).padStart(2, '0') + ':' + String(m % 60).padStart(2, '0');
  const tgAtLeast = v => inTelegram && typeof tg.isVersionAtLeast === 'function' && tg.isVersionAtLeast(v);
  function haptic(kind) {
    if (!tgAtLeast('6.1') || !tg.HapticFeedback) return;
    try { kind === 'light' ? tg.HapticFeedback.impactOccurred('light') : tg.HapticFeedback.notificationOccurred(kind); } catch (e) { /* мелочь */ }
  }
  function hexToSoft(hex, alpha) {
    const m = /^#?([0-9a-f]{6})$/i.exec(hex || '');
    if (!m) return null;
    const n = parseInt(m[1], 16);
    return `rgba(${n >> 16}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
  }

  // Время в часовом поясе заведения (а не в часовом поясе телефона клиента).
  function minutesNow() {
    try {
      const parts = new Intl.DateTimeFormat('en-GB', { timeZone: state.data.timezone || 'Europe/Moscow',
        hour: '2-digit', minute: '2-digit', hour12: false }).formatToParts(new Date());
      const get = t => Number(parts.find(p => p.type === t).value);
      return (get('hour') % 24) * 60 + get('minute');
    } catch (e) {
      const d = new Date();
      return d.getHours() * 60 + d.getMinutes();
    }
  }
  function openInfo() {
    const h = state.data.hours || {};
    const open = toMin(h.open), close = toMin(h.close), now = minutesNow();
    const isOpen = close > open ? now >= open && now < close : true;
    return { open, close, now, isOpen, h };
  }
  function timeOptions() {
    const { open, close, now, isOpen } = openInfo();
    const opts = [];
    if (isOpen) opts.push('Как можно скорее');
    let start, day;
    if (isOpen) { start = Math.ceil((now + 30) / 30) * 30; day = 'Сегодня'; }
    else if (now < open) { start = open; day = 'Сегодня'; }
    else { start = open; day = 'Завтра'; }
    for (let t = start; t <= close - 30 && opts.length < 30; t += 30) opts.push(`${day}, ${hhmm(t)}`);
    if (!opts.length || (isOpen && opts.length === 1)) {
      for (let t = open; t <= close - 30 && opts.length < 30; t += 30) opts.push(`Завтра, ${hhmm(t)}`);
    }
    return opts;
  }
  function normPhone(s) {
    const d = String(s || '').replace(/\D/g, '');
    let n = null;
    if (d.length === 11 && (d[0] === '7' || d[0] === '8')) n = d.slice(1);
    else if (d.length === 10 && d[0] === '9') n = d;
    return n ? `+7 ${n.slice(0, 3)} ${n.slice(3, 6)}-${n.slice(6, 8)}-${n.slice(8)}` : null;
  }
  const cartCount = () => [...state.cart.values()].reduce((a, b) => a + b, 0);
  const cartTotal = () => [...state.cart].reduce((sum, [id, q]) => sum + (state.items.get(id).price || 0) * q, 0);

  // ---------- загрузка ----------
  async function load() {
    try {
      const res = await fetch('data.json', { cache: 'no-cache' });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const data = await res.json();
      if (!data || !Array.isArray(data.categories)) throw new Error('нет меню');
      state.data = data;
      for (const cat of data.categories) for (const it of cat.items || []) {
        if (it && it.id && it.name) state.items.set(String(it.id), it);
      }
      if (data.pickup === false && data.delivery) state.mode = 'delivery';
      start();
    } catch (e) {
      const app = document.getElementById('app');
      app.replaceChildren(el('div', { class: 'loading' },
        el('p', { text: 'Не удалось загрузить меню. Проверьте интернет и попробуйте ещё раз.' }),
        el('button', { class: 'btn', type: 'button', style: 'max-width:260px', onclick: () => location.reload(), text: 'Обновить' })));
    }
  }

  // ---------- каркас ----------
  function start() {
    const d = state.data;
    document.title = d.name || 'Меню';
    const root = document.documentElement;
    if (inTelegram) root.classList.add('tg');
    if (d.accent) {
      root.style.setProperty('--accent', d.accent);
      const soft = hexToSoft(d.accent, 0.14);
      if (soft) root.style.setProperty('--accent-soft', soft);
    }
    const app = document.getElementById('app');
    app.replaceChildren(document.getElementById('tpl-shell').content.cloneNode(true));
    for (const node of app.querySelectorAll('[data-bind]')) shell[node.dataset.bind] = node;
    for (const node of app.querySelectorAll('[data-screen]')) shell['screen_' + node.dataset.screen] = node;
    shell.tabs = app.querySelector('.tabs');
    shell.logo.textContent = d.logo || '🛍️';
    shell.name.textContent = d.name || '';
    shell.tagline.textContent = d.tagline || '';
    shell.address.textContent = d.address || '';
    const info = openInfo();
    shell.status.textContent = info.isOpen ? `Открыто до ${info.h.close}` : `Закрыто · откроемся в ${info.h.open}`;
    shell.status.classList.toggle('is-closed', !info.isOpen);
    for (const btn of app.querySelectorAll('[data-tab]')) btn.addEventListener('click', () => show(btn.dataset.tab));
    shell.bar.addEventListener('click', primaryAction);

    if (!inTelegram) {
      shell.demo.hidden = false;
      shell.demo.textContent = 'Демо-режим: так приложение выглядит в Telegram. Отправить заказ можно из чата с ботом.';
    } else if (!canSend) {
      shell.demo.hidden = false;
      shell.demo.textContent = 'Чтобы отправить заказ, откройте приложение кнопкой под полем ввода в чате с ботом.';
    }
    renderMenu();
    renderAbout();

    if (inTelegram) {
      tg.ready();
      tg.expand();
      tg.MainButton.setParams({ color: d.accent || tg.themeParams.button_color, text_color: '#ffffff' });
      tg.MainButton.onClick(primaryAction);
      if (tgAtLeast('6.1')) tg.BackButton.onClick(() => show('menu'));
    }
    updateButtons();
  }

  function show(screen) {
    state.screen = screen;
    for (const name of ['menu', 'about', 'cart']) shell['screen_' + name].hidden = name !== screen;
    shell.tabs.hidden = screen === 'cart';
    for (const btn of shell.tabs.querySelectorAll('[data-tab]')) {
      const on = btn.dataset.tab === screen;
      btn.classList.toggle('is-active', on);
      btn.setAttribute('aria-selected', String(on));
    }
    if (screen === 'cart') renderCart();
    if (inTelegram && tgAtLeast('6.1')) screen === 'cart' ? tg.BackButton.show() : tg.BackButton.hide();
    window.scrollTo(0, 0);
    updateButtons();
  }

  function primaryAction() {
    if (state.screen !== 'cart') { if (cartCount()) show('cart'); return; }
    submit();
  }

  function updateButtons() {
    const count = cartCount();
    let text = '', visible = false;
    if (state.screen === 'cart') { visible = count > 0; text = `Отправить заказ · ${money(cartTotal())}`; }
    else if (count) { visible = true; text = `Корзина · ${count} шт. · ${money(cartTotal())}`; }
    if (inTelegram) {
      visible ? tg.MainButton.setText(text).show() : tg.MainButton.hide();
      if (tgAtLeast('6.2')) count ? tg.enableClosingConfirmation() : tg.disableClosingConfirmation();
      shell.bar.hidden = true;
    } else {
      shell.bar.hidden = !visible;
      shell.bar.textContent = text;
    }
  }

  // ---------- меню ----------
  function control(id) {
    const q = state.cart.get(id) || 0;
    const it = state.items.get(id);
    if (!q) return el('button', { class: 'add', type: 'button', 'aria-label': `Добавить «${it.name}»`, onclick: () => change(id, 1), text: '+' });
    return el('div', { class: 'stepper' },
      el('button', { type: 'button', 'aria-label': 'Меньше', onclick: () => change(id, -1), text: '−' }),
      el('span', { text: String(q) }),
      el('button', { type: 'button', 'aria-label': 'Больше', onclick: () => change(id, 1), text: '+' }));
  }

  function change(id, delta) {
    const q = Math.max(0, Math.min(99, (state.cart.get(id) || 0) + delta));
    q ? state.cart.set(id, q) : state.cart.delete(id);
    haptic('light');
    const slot = shell.screen_menu.querySelector(`[data-ctl="${CSS.escape(id)}"]`);
    if (slot) slot.replaceChildren(control(id));
    if (state.screen === 'cart') { if (!cartCount()) show('menu'); else renderCart(); }
    updateButtons();
  }

  function renderMenu() {
    const box = shell.screen_menu;
    box.replaceChildren();
    for (const cat of state.data.categories) {
      const items = (cat.items || []).filter(it => state.items.has(String(it.id)));
      if (!items.length) continue;
      box.append(el('h2', { class: 'cat', text: cat.title || '' }));
      for (const it of items) {
        const id = String(it.id);
        box.append(el('article', { class: 'item' },
          el('div', { class: 'item__pic', 'aria-hidden': 'true', text: it.emoji || '•' }),
          el('div', {},
            el('h3', { class: 'item__name', text: it.name }),
            it.desc ? el('p', { class: 'item__desc', text: it.desc }) : null,
            el('div', { class: 'item__price', text: money(it.price || 0) })),
          el('div', { 'data-ctl': id }, control(id))));
      }
    }
  }

  // ---------- о нас ----------
  function renderAbout() {
    const d = state.data, h = d.hours || {};
    const box = shell.screen_about;
    box.replaceChildren(
      el('div', { class: 'card' },
        el('h3', { text: 'Как нас найти' }),
        el('p', { class: 'row' }, el('b', { text: 'Адрес' }), el('span', { text: d.address || '—' })),
        el('p', { class: 'row' }, el('b', { text: 'Часы' }), el('span', { text: `${h.days || ''} ${h.open || ''}–${h.close || ''}`.trim() })),
        d.delivery ? el('p', { class: 'row' }, el('b', { text: 'Доставка' }), el('span', { text: d.delivery_note || 'Есть, детали уточнит менеджер.' })) : null),
      el('div', { class: 'card' },
        el('h3', { text: 'О нас' }),
        ...(d.about || []).map(t => el('p', { text: t }))),
      el('div', { class: 'card' },
        el('h3', { text: 'Как заказать' }),
        el('p', { text: '1. Добавьте в корзину то, что хотите.' }),
        el('p', { text: '2. Откройте корзину и укажите имя, телефон и время.' }),
        el('p', { text: '3. Отправьте заказ — менеджер свяжется с вами и подтвердит его.' })),
      inTelegram ? el('button', { class: 'btn btn--ghost', type: 'button', onclick: () => tg.close(), text: 'Задать вопрос в чате' }) : null);
  }

  // ---------- корзина и оформление ----------
  function field(key, label, input, hint) {
    const wrap = el('label', { class: 'field' + (state.errors[key] ? ' is-error' : ''), 'data-field': key },
      el('span', { text: label }), input, el('div', { class: 'err', text: state.errors[key] || '' }));
    if (hint) wrap.append(el('div', { class: 'muted', style: 'margin:5px 0 0 2px', text: hint }));
    return wrap;
  }
  function bindInput(node, key) {
    node.value = state.form[key];
    node.addEventListener('input', () => {
      state.form[key] = node.value;
      if (state.errors[key]) { delete state.errors[key]; node.closest('.field').classList.remove('is-error'); }
    });
    return node;
  }

  function renderCart() {
    const d = state.data;
    const box = shell.screen_cart;
    if (!cartCount()) { box.replaceChildren(el('p', { class: 'empty', text: 'Корзина пуста' })); return; }
    const lines = [...state.cart].map(([id, q]) => {
      const it = state.items.get(id);
      return el('div', { class: 'line' },
        el('div', {}, el('div', { text: `${it.emoji || ''} ${it.name}`.trim() }), el('div', { class: 'muted', text: money(it.price || 0) })),
        el('div', { class: 'stepper' },
          el('button', { type: 'button', 'aria-label': 'Меньше', onclick: () => change(id, -1), text: '−' }),
          el('span', { text: String(q) }),
          el('button', { type: 'button', 'aria-label': 'Больше', onclick: () => change(id, 1), text: '+' })),
        el('div', { class: 'line__sum', text: money((it.price || 0) * q) }));
    });

    const modes = [];
    if (d.pickup !== false) modes.push(['pickup', 'Самовывоз']);
    if (d.delivery) modes.push(['delivery', 'Доставка']);
    const seg = modes.length > 1 ? el('div', { class: 'seg', role: 'radiogroup' }, ...modes.map(([value, label]) =>
      el('button', { type: 'button', class: state.mode === value ? 'is-on' : '', role: 'radio',
                     'aria-checked': String(state.mode === value),
                     onclick: () => { state.mode = value; delete state.errors.address; renderCart(); }, text: label }))) : null;

    const times = timeOptions();
    if (!times.includes(state.form.time)) state.form.time = times[0] || '';
    const timeSelect = el('select', {}, ...times.map(t => el('option', { value: t, text: t })));
    timeSelect.value = state.form.time;
    timeSelect.addEventListener('change', () => { state.form.time = timeSelect.value; });

    // В Telegram назад ведёт его собственная кнопка «Назад» в шапке; в браузере и старых версиях Telegram — эта.
    const back = inTelegram && tgAtLeast('6.1') ? null
      : el('button', { class: 'btn btn--ghost', type: 'button', style: 'margin-bottom:12px', onclick: () => show('menu'), text: '← Назад к меню' });
    box.replaceChildren(
      back,
      el('div', { class: 'card' }, el('h3', { text: 'Ваш заказ' }), ...lines,
        el('div', { class: 'total' }, el('span', { text: 'Итого' }), el('span', { text: money(cartTotal()) }))),
      el('div', { class: 'card' },
        el('h3', { text: 'Получение' }),
        seg,
        state.mode === 'delivery'
          ? field('address', 'Адрес доставки', bindInput(el('input', { type: 'text', autocomplete: 'street-address', maxlength: '200', placeholder: 'Улица, дом, квартира' }), 'address'), d.delivery_note)
          : el('p', { class: 'muted', style: 'margin:10px 2px 0', text: `Заберите заказ по адресу: ${d.address || ''}` }),
        field('time', 'Когда', timeSelect)),
      el('div', { class: 'card' },
        el('h3', { text: 'Контакты' }),
        field('name', 'Имя', bindInput(el('input', { type: 'text', autocomplete: 'given-name', maxlength: '60', placeholder: 'Как к вам обращаться' }), 'name')),
        field('phone', 'Телефон', bindInput(el('input', { type: 'tel', inputmode: 'tel', autocomplete: 'tel', maxlength: '20', placeholder: '+7 900 123-45-67' }), 'phone')),
        field('comment', 'Комментарий (необязательно)', bindInput(el('textarea', { maxlength: '300', placeholder: 'Например: без сахара' }), 'comment'))),
      el('p', { class: 'muted', style: 'margin:0 4px', text: 'Отправляя заказ, вы передаёте имя и телефон заведению, чтобы менеджер связался с вами.' }));
    if (!state.form.name && inTelegram && tg.initDataUnsafe && tg.initDataUnsafe.user) {
      state.form.name = tg.initDataUnsafe.user.first_name || '';
      const nameInput = box.querySelector('[data-field="name"] input');
      if (nameInput) nameInput.value = state.form.name;
    }
  }

  function validate() {
    const f = state.form, e = {};
    if (f.name.trim().length < 2) e.name = 'Напишите, как к вам обращаться';
    if (!normPhone(f.phone)) e.phone = 'Нужен номер вида +7 900 123-45-67';
    if (state.mode === 'delivery' && f.address.trim().length < 5) e.address = 'Укажите адрес доставки';
    state.errors = e;
    return Object.keys(e);
  }

  function buildPayload() {
    const f = state.form;
    const payload = {
      v: 1, type: 'order', currency: state.data.currency || '₽',
      items: [...state.cart].map(([id, q]) => { const it = state.items.get(id); return { name: it.name, qty: q, price: it.price || 0 }; }),
      total: cartTotal(), mode: state.mode,
      address: state.mode === 'delivery' ? f.address.trim() : '',
      time: f.time, name: f.name.trim(), phone: normPhone(f.phone), comment: f.comment.trim(),
    };
    let json = JSON.stringify(payload);
    const size = s => new TextEncoder().encode(s).length;
    while (size(json) > MAX_BYTES && payload.comment) { payload.comment = payload.comment.slice(0, -20); json = JSON.stringify(payload); }
    while (size(json) > MAX_BYTES && payload.items.length > 1) { payload.items.pop(); json = JSON.stringify(payload); }
    return json;
  }

  function submit() {
    const bad = validate();
    if (bad.length) {
      renderCart();
      haptic('error');
      const first = shell.screen_cart.querySelector(`[data-field="${bad[0]}"]`);
      if (first) { first.scrollIntoView({ behavior: 'smooth', block: 'center' }); const inp = first.querySelector('input,textarea'); if (inp) inp.focus(); }
      return;
    }
    const json = buildPayload();
    if (canSend) {
      try { haptic('success'); tg.sendData(json); }          // Telegram отправит заказ боту и сам закроет приложение
      catch (e) { sheet('Не получилось отправить', 'Попробуйте ещё раз или напишите заказ прямо в чат.'); }
      return;
    }
    if (inTelegram) {
      sheet('Откройте приложение из чата', 'Закройте это окно и нажмите кнопку приложения под полем ввода в чате с ботом — оттуда заказ отправится.');
      return;
    }
    sheet('Демо-режим', 'В Telegram этот заказ сразу ушёл бы боту, а менеджер получил бы заявку. Вот что отправится:',
          JSON.stringify(JSON.parse(json), null, 2));
  }

  function sheet(title, text, pre) {
    const s = document.getElementById('sheet');
    document.getElementById('sheet-title').textContent = title;
    document.getElementById('sheet-text').textContent = text;
    const p = document.getElementById('sheet-pre');
    p.hidden = !pre;
    p.textContent = pre || '';
    s.hidden = false;
    document.getElementById('sheet-close').focus();
  }
  document.getElementById('sheet-close').addEventListener('click', () => { document.getElementById('sheet').hidden = true; });
  document.getElementById('sheet').addEventListener('click', e => { if (e.target.id === 'sheet') e.target.hidden = true; });

  load();
})();

// Общее для всех страниц: шапка, подвал, меню, анимации, маска телефона.
const PAGES = [['index.html', 'Главная'], ['services.html', 'Услуги и цены'], ['about.html', 'О сервисе'], ['contacts.html', 'Контакты']];
const here = location.pathname.split('/').pop() || 'index.html';
const GEAR = '<svg width="20" height="20" viewBox="0 0 24 24"><path d="M12 8.5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7z" fill="none" stroke="#121417" stroke-width="2.2"/><path d="M12 2v3M12 19v3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M2 12h3M19 12h3M4.9 19.1 7 17M17 7l2.1-2.1" stroke="#121417" stroke-width="2.2" stroke-linecap="round"/></svg>';

document.getElementById('top').outerHTML = `<header class="top" id="top"><div class="wrap">
  <a class="logo" href="index.html"><i>${GEAR}</i>ТОРК</a>
  <nav class="nav" id="nav">${PAGES.map(([h, t]) => `<a href="${h}" class="${h === here ? 'on' : ''}">${t}</a>`).join('')}</nav>
  <div class="phone"><b>+7 (900) 000-00-00</b><span>ежедневно 8:00–21:00</span></div>
  <a class="btn btn-y" href="booking.html">Записаться</a>
  <button class="burger" id="burger" aria-label="Меню"><span></span><span></span><span></span></button></div></header>`;

document.getElementById('foot').outerHTML = `<footer><div class="wrap">
  <div class="foot">
    <div><a class="logo" href="index.html"><i>${GEAR}</i>ТОРК</a><p>Автосервис полного цикла: от замены масла до ремонта двигателя. Цена — до начала работ, фотоотчёт — в Telegram.</p></div>
    <div><h4>Страницы</h4>${PAGES.map(([h, t]) => `<a href="${h}">${t}</a>`).join('')}<a href="booking.html">Онлайн-запись</a></div>
    <div><h4>Контакты</h4><a href="contacts.html">ул. Моторная, 7</a><a href="contacts.html">+7 (900) 000-00-00</a></div>
    <div><h4>Часы работы</h4><p style="line-height:2">Пн–Пт 8:00–21:00<br>Сб–Вс 9:00–19:00</p></div>
  </div>
  <div class="legal"><span>© 2026 Автосервис «ТОРК»</span><span>Концепт многостраничного сайта для портфолио: компания, цены и отзывы вымышленные</span></div></div></footer>`;

document.getElementById('burger').onclick = () => document.getElementById('top').classList.toggle('open');

const io = new IntersectionObserver((es) => es.forEach((e) => { if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); } }), { threshold: 0.12 });
document.querySelectorAll('.reveal').forEach((el) => io.observe(el));

// маска телефона для всех полей type=tel
function phoneMask(inp) {
  inp.addEventListener('input', () => {
    const d = inp.value.replace(/\D/g, '').replace(/^[78]/, '').slice(0, 10);
    const p = [d.slice(0, 3), d.slice(3, 6), d.slice(6, 8), d.slice(8, 10)];
    inp.value = d ? `+7 (${p[0]}${d.length > 3 ? ') ' + p[1] : ''}${d.length > 6 ? '-' + p[2] : ''}${d.length > 8 ? '-' + p[3] : ''}` : '';
    inp.classList.remove('bad');
  });
}
document.querySelectorAll('input[type=tel]').forEach(phoneMask);
const phoneOk = (inp) => inp.value.replace(/\D/g, '').length === 11;

// иконки услуг (общие для главной, услуг и записи)
const ICONS = {
  to: '<path d="M12 3s6 6.5 6 10.5A6 6 0 0 1 6 13.5C6 9.5 12 3 12 3z" fill="none" stroke="currentColor" stroke-width="2"/><path d="M9.5 14a2.5 2.5 0 0 0 2.5 2.5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>',
  engine: '<path d="M4 9h3l2-2h5v2h3l2 2v6h-3l-2 2H9l-2-2H4z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/><path d="M2 11v4M21 12h1" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>',
  susp: '<path d="M12 3v3M12 18v3M8 7h8M8 17h8" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><path d="M9 7l6 2.5-6 2.5 6 2.5-6 2.5" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>',
  brake: '<circle cx="12" cy="12" r="8" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="12" cy="12" r="2.5" fill="none" stroke="currentColor" stroke-width="2"/><path d="M18 6.5a8 8 0 0 1 0 11" stroke="currentColor" stroke-width="4" stroke-linecap="round" fill="none"/>',
  tire: '<circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="12" cy="12" r="4" fill="none" stroke="currentColor" stroke-width="2"/><path d="M12 3v5M12 16v5M3 12h5M16 12h5" stroke="currentColor" stroke-width="2"/>',
  ac: '<path d="M12 2v20M3.3 7l17.4 10M3.3 17 20.7 7" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><path d="M9 4l3 2 3-2M9 20l3-2 3 2" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>',
  elec: '<rect x="3" y="7" width="18" height="12" rx="2" fill="none" stroke="currentColor" stroke-width="2"/><path d="M7 7V5M17 7V5M7 13h3M15.5 11.5v3M14 13h3" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>',
  diag: '<rect x="3" y="4" width="18" height="13" rx="2" fill="none" stroke="currentColor" stroke-width="2"/><path d="M6 12h3l1.5-3 2 5 1.5-2H18M9 21h6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>',
};
const icon = (k, c = '#121417') => `<svg viewBox="0 0 24 24" style="color:${c}">${ICONS[k]}</svg>`;

// прайс (общий для страниц «Услуги» и «Запись»)
const CATS = [
  ['to', 'Техобслуживание', [['Замена масла и масляного фильтра', '30 мин', 900], ['Замена воздушного фильтра', '15 мин', 300], ['Замена салонного фильтра', '20 мин', 400], ['ТО по регламенту (без запчастей)', '2 ч', 3500], ['Замена свечей зажигания', '40 мин', 800]]],
  ['diag', 'Диагностика', [['Компьютерная диагностика', '30 мин', 1000], ['Диагностика ходовой', '40 мин', 800], ['Проверка перед покупкой авто', '1,5 ч', 2500]]],
  ['brake', 'Тормоза', [['Замена передних колодок', '40 мин', 1200], ['Замена задних колодок', '1 ч', 1500], ['Замена тормозных дисков (ось)', '1,5 ч', 2400], ['Замена тормозной жидкости', '1 ч', 1300]]],
  ['susp', 'Подвеска', [['Замена амортизатора', '1 ч', 1800], ['Замена рычага', '1 ч', 1600], ['Замена стойки стабилизатора', '30 мин', 700], ['Развал-схождение', '1 ч', 2000]]],
  ['engine', 'Двигатель', [['Замена ремня ГРМ', '3 ч', 6000], ['Замена помпы', '2 ч', 3500], ['Замена прокладки клапанной крышки', '1,5 ч', 2200], ['Промывка инжектора', '1,5 ч', 3000]]],
  ['tire', 'Шиномонтаж', [['Сезонная переобувка (4 колеса)', '40 мин', 2400], ['Балансировка колеса', '10 мин', 350], ['Ремонт прокола', '20 мин', 600], ['Хранение шин (сезон)', '—', 3000]]],
  ['ac', 'Кондиционер', [['Заправка кондиционера', '40 мин', 2200], ['Антибактериальная обработка', '30 мин', 1500], ['Поиск утечки фреона', '1 ч', 1800]]],
  ['elec', 'Электрика', [['Замена аккумулятора', '20 мин', 500], ['Ремонт проводки', '1 ч', 1500], ['Установка сигнализации', '3 ч', 5000]]],
];
const rub = (n) => n.toLocaleString('ru-RU') + ' ₽';
